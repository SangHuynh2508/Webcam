"""
ai_engine.py — Skeleton AI Engine loading 3 models.
Phase 1: Load all models + anchor embeddings into RAM.
Phase 3: Only ArcFace verify_identity() is fully implemented.
         MediaPipe & YOLO are placeholders.
"""
import os
import logging
import numpy as np
import cv2
from sklearn.metrics.pairwise import cosine_similarity

from backend.config import (
    ANCHOR_DIR,
    FACE_DETECTION_MODEL,
    FACE_SIMILARITY_THRESHOLD,
    YOLO_MODEL_PATH,
    CUSTOM_YOLO_MODEL_PATH,
    FACE_LANDMARKER_MODEL_PATH,
)

logger = logging.getLogger("anti_cheat.ai_engine")


class AIEngine:
    """Central AI processing unit. Loads models once at startup."""

    def __init__(self):
        self.face_analyzer = None    # insightface FaceAnalysis
        self.face_landmarker = None  # mediapipe FaceLandmarker
        self.object_detector = None  # ultralytics YOLO (COCO)
        self.custom_detector = None  # ultralytics YOLO (custom: calculator)
        self.anchor_db: dict = {}    # {MSSV: {"name": str, "embedding": np.ndarray}}

    # ------------------------------------------------------------------
    # Phase 1: Model Loading
    # ------------------------------------------------------------------

    def load_models(self):
        """Load all 3 AI models into RAM. Called once at server startup."""
        self._load_arcface()
        self._load_mediapipe()
        self._load_yolo()
        self._load_custom_yolo()

    def _load_arcface(self):
        """Load InsightFace ArcFace model (ResNet100)."""
        try:
            import insightface
            self.face_analyzer = insightface.app.FaceAnalysis(
                name=FACE_DETECTION_MODEL,
                providers=["CPUExecutionProvider"],
            )
            self.face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("[ArcFace] Model loaded successfully.")
        except Exception as e:
            logger.error(f"[ArcFace] Failed to load: {e}")
            raise

    def _load_mediapipe(self):
        """Load MediaPipe FaceLandmarker (Tasks API) for head pose estimation."""
        try:
            if not os.path.exists(FACE_LANDMARKER_MODEL_PATH):
                logger.warning(f"[MediaPipe] Model not found: {FACE_LANDMARKER_MODEL_PATH}")
                return

            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import (
                FaceLandmarker,
                FaceLandmarkerOptions,
            )

            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=FACE_LANDMARKER_MODEL_PATH),
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                output_facial_transformation_matrixes=True,
            )
            self.face_landmarker = FaceLandmarker.create_from_options(options)
            logger.info("[MediaPipe] FaceLandmarker (Tasks API) loaded successfully.")
        except Exception as e:
            logger.warning(f"[MediaPipe] Failed to load (non-blocking): {e}")

    def _load_yolo(self):
        """Load YOLOv8 Nano for forbidden object detection."""
        try:
            from ultralytics import YOLO
            self.object_detector = YOLO(YOLO_MODEL_PATH)
            logger.info("[YOLOv8] COCO model loaded successfully.")
        except Exception as e:
            logger.warning(f"[YOLOv8] Failed to load COCO model (non-blocking): {e}")

    def _load_custom_yolo(self):
        """Load custom YOLOv8 model for calculator detection."""
        try:
            import os
            if not os.path.exists(CUSTOM_YOLO_MODEL_PATH):
                logger.warning(f"[YOLOv8-Custom] Model not found: {CUSTOM_YOLO_MODEL_PATH}")
                return
            from ultralytics import YOLO
            self.custom_detector = YOLO(CUSTOM_YOLO_MODEL_PATH)
            class_names = list(self.custom_detector.names.values())
            logger.info(f"[YOLOv8-Custom] Loaded successfully. Classes: {class_names}")
        except Exception as e:
            logger.warning(f"[YOLOv8-Custom] Failed to load (non-blocking): {e}")

    # ------------------------------------------------------------------
    # Phase 1: Anchor Embedding Extraction
    # ------------------------------------------------------------------

    def load_anchors(self, anchor_dir: str = ANCHOR_DIR):
        """
        Scan anchor directory and extract ArcFace embeddings.
        Expected filename format: MSSV_HoTen.jpg
        Stores in self.anchor_db = {MSSV: {"name": str, "embedding": ndarray}}
        """
        if not os.path.isdir(anchor_dir):
            logger.warning(f"[Anchor] Directory not found: {anchor_dir}")
            os.makedirs(anchor_dir, exist_ok=True)
            return

        loaded = 0
        skipped = 0

        for filename in os.listdir(anchor_dir):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            name_part = os.path.splitext(filename)[0]
            parts = name_part.split("_", 1)

            if len(parts) < 2:
                logger.warning(f"[Anchor] Invalid filename format: {filename} (expected MSSV_Name)")
                skipped += 1
                continue

            mssv = parts[0]
            name = parts[1].replace("_", " ")

            filepath = os.path.join(anchor_dir, filename)
            img = cv2.imread(filepath)

            if img is None:
                logger.warning(f"[Anchor] Cannot read image: {filepath}")
                skipped += 1
                continue

            faces = self.face_analyzer.get(img)

            if not faces:
                logger.warning(f"[Anchor] No face detected in: {filename}")
                skipped += 1
                continue

            embedding = faces[0].embedding
            self.anchor_db[mssv] = {
                "name": name,
                "embedding": embedding,
            }
            loaded += 1

        logger.info(f"[Anchor] Loaded: {loaded} | Skipped: {skipped} | Total in DB: {len(self.anchor_db)}")

    def load_db_anchors(self, db_session, room_id: int):
        """
        Load student reference face embeddings for a specific exam room from the database.
        If embedding is not serialized yet, dynamically extract it from the image and cache it in the DB.
        """
        from backend.models import RoomStudent
        
        logger.info(f"[Anchor] Loading database anchors for room_id={room_id}...")
        
        enrollments = db_session.query(RoomStudent).filter(RoomStudent.room_id == room_id).all()
        loaded = 0
        skipped = 0
        
        for enroll in enrollments:
            student = enroll.student
            if not student or not student.mssv:
                continue
                
            mssv = student.mssv
            embedding_list = enroll.get_embedding()
            
            if embedding_list is not None:
                # Use cached embedding
                self.anchor_db[mssv] = {
                    "name": student.full_name,
                    "embedding": np.array(embedding_list, dtype=np.float32),
                }
                loaded += 1
            elif enroll.face_image_path and os.path.exists(enroll.face_image_path):
                # Fallback: extract embedding dynamically and cache it
                img = cv2.imread(enroll.face_image_path)
                if img is not None:
                    faces = self.face_analyzer.get(img)
                    if faces:
                        embedding = faces[0].embedding
                        enroll.set_embedding(embedding)
                        db_session.add(enroll)
                        
                        self.anchor_db[mssv] = {
                            "name": student.full_name,
                            "embedding": embedding,
                        }
                        loaded += 1
                        continue
                logger.warning(f"[Anchor] Cannot read image path: {enroll.face_image_path}")
                skipped += 1
            else:
                logger.warning(f"[Anchor] Missing face embedding and photo for student: {student.full_name}")
                skipped += 1
                
        db_session.commit()
        logger.info(f"[Anchor] Successfully loaded {loaded} anchors from DB for room {room_id}. Skipped: {skipped}")

    # ------------------------------------------------------------------
    # Phase 3: ArcFace Identity Verification (FULLY IMPLEMENTED)
    # ------------------------------------------------------------------

    def load_room_anchors(self, anchors: list):
        """
        Load student reference face embeddings directly from the provided list
        of anchor documents. This is used when starting an exam.
        """
        loaded = 0
        skipped = 0
        for anchor in anchors:
            mssv = anchor.get("student_id")
            if not mssv:
                continue
            
            embedding_list = anchor.get("face_embedding")
            if embedding_list and len(embedding_list) > 0:
                self.anchor_db[mssv] = {
                    "name": mssv,
                    "embedding": np.array(embedding_list, dtype=np.float32),
                }
                loaded += 1
            else:
                logger.warning(f"[Anchor] Missing face embedding for student {mssv}")
                skipped += 1
                
        logger.info(f"[Anchor] Successfully loaded {loaded} anchors from memory. Skipped: {skipped}")


    def verify_identity(self, frame: np.ndarray, mssv: str, threshold: float = None) -> dict:
        """
        Phát hiện khuôn mặt to nhất trong frame và so khớp Cosine Similarity
        với embedding của mssv được cung cấp trong RAM (self.anchor_db).
        Returns: {"status": str, "name": str, "similarity": float}
        """
        if mssv not in self.anchor_db:
            return {
                "status": "Error",
                "name": "Chưa đăng ký",
                "similarity": 0.0,
            }

        # 1. Phát hiện khuôn mặt trong frame đầu vào
        faces = self.face_analyzer.get(frame)

        # Trạng thái 1: Không có khuôn mặt nào trong frame
        if not faces:
            return {
                "status": "No Face",
                "name": "None",
                "similarity": 0.0,
                "face_bbox": None,
            }

        # 2. Tìm khuôn mặt to nhất (dựa trên diện tích bounding box)
        largest_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        # Trích xuất bbox và chuẩn hóa về tỷ lệ 0-1 (để frontend vẽ trên mọi kích thước)
        h, w = frame.shape[:2]
        raw_bbox = largest_face.bbox  # [x1, y1, x2, y2] dạng pixel
        face_bbox = {
            "x1": round(float(raw_bbox[0]) / w, 4),
            "y1": round(float(raw_bbox[1]) / h, 4),
            "x2": round(float(raw_bbox[2]) / w, 4),
            "y2": round(float(raw_bbox[3]) / h, 4),
        }
        
        # Reshape thành mảng 2D (1, 512) để tính cosine_similarity
        current_embedding = largest_face.embedding.reshape(1, -1)

        # 3. Tính cosine similarity với mssv cụ thể
        target_data = self.anchor_db[mssv]
        anchor_embedding = target_data["embedding"].reshape(1, -1)
        sim = float(cosine_similarity(current_embedding, anchor_embedding)[0][0])

        # 4. Kiểm tra với Threshold để quyết định kết quả
        t = threshold if threshold is not None else FACE_SIMILARITY_THRESHOLD
        if sim > t:
            # Trạng thái 2: Khuôn mặt trùng khớp
            return {
                "status": "Match",
                "name": target_data["name"],
                "similarity": round(sim, 4),
                "face_bbox": face_bbox,
            }
        else:
            # Trạng thái 3: Sai người / Người lạ
            return {
                "status": "Unknown",
                "name": "Sai người",
                "similarity": round(sim, 4),
                "face_bbox": face_bbox,
            }

    # ------------------------------------------------------------------
    # Phase 3: MediaPipe Head Pose Estimation (FULLY IMPLEMENTED)
    # ------------------------------------------------------------------

    # 6 canonical 3D face model points (nose tip, chin, left/right eye corners, left/right mouth corners)
    # Based on a generic anthropometric face model (units: arbitrary, relative scale matters)
    _FACE_3D_MODEL = np.array([
        [0.0, 0.0, 0.0],         # Nose tip
        [0.0, -330.0, -65.0],     # Chin
        [-225.0, 170.0, -135.0],  # Left eye left corner
        [225.0, 170.0, -135.0],   # Right eye right corner
        [-150.0, -150.0, -125.0], # Left mouth corner
        [150.0, -150.0, -125.0],  # Right mouth corner
    ], dtype=np.float64)

    # Corresponding MediaPipe FaceMesh landmark indices (0-467)
    _LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]

    def analyze_head_pose(
        self,
        frame: np.ndarray,
        yaw_threshold: float = None,
        pitch_threshold: float = None,
    ) -> dict | None:
        """
        Analyze head orientation (Yaw, Pitch, Roll) using MediaPipe FaceLandmarker (Tasks API) + cv2.solvePnP.
        Returns: {"yaw": float, "pitch": float, "roll": float, "alert": str|None}
        """
        if self.face_landmarker is None:
            return None

        from backend.config import HEAD_YAW_THRESHOLD, HEAD_PITCH_THRESHOLD

        yaw_t = yaw_threshold if yaw_threshold is not None else HEAD_YAW_THRESHOLD
        pitch_t = pitch_threshold if pitch_threshold is not None else HEAD_PITCH_THRESHOLD

        h, w = frame.shape[:2]

        # Convert BGR → RGB and wrap in MediaPipe Image
        import mediapipe as mp
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Detect face landmarks using Tasks API
        results = self.face_landmarker.detect(mp_image)

        if not results.face_landmarks:
            return None

        face_landmarks = results.face_landmarks[0]

        # Extract 2D image points from the 6 key landmarks
        image_points = np.array([
            [face_landmarks[idx].x * w, face_landmarks[idx].y * h]
            for idx in self._LANDMARK_INDICES
        ], dtype=np.float64)

        # Synthetic camera intrinsic matrix (assume no lens distortion)
        focal_length = w
        center = (w / 2.0, h / 2.0)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        # Solve PnP → rotation vector
        success, rotation_vector, _ = cv2.solvePnP(
            self._FACE_3D_MODEL,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success:
            return None

        # Convert rotation vector → rotation matrix → Euler angles
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        # Decompose rotation matrix into projection matrices to extract angles
        proj_matrix = np.hstack((rotation_matrix, np.zeros((3, 1))))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        pitch = float(euler_angles[0][0])  # Cúi/ngẩng (up/down)
        yaw = float(euler_angles[1][0])    # Liếc ngang (left/right)
        roll = float(euler_angles[2][0])   # Nghiêng vai (tilt)

        # Chuẩn hóa góc Euler về khoảng [-90, 90] để tránh hiện tượng Gimbal Lock
        # (cv2.decomposeProjectionMatrix có thể trả về góc ~180° khi thực tế chỉ nghiêng nhẹ)
        def normalize_angle(angle):
            if angle > 90:
                return angle - 180
            elif angle < -90:
                return angle + 180
            return angle

        pitch = normalize_angle(pitch)
        yaw = normalize_angle(yaw)
        roll = normalize_angle(roll)

        # Build alert message if thresholds exceeded
        alert = None
        alerts_parts = []

        if abs(yaw) > yaw_t:
            direction = "trái" if yaw < 0 else "phải"
            alerts_parts.append(f"Liếc {direction} ({abs(yaw):.1f}°)")

        if abs(pitch) > pitch_t:
            direction = "cúi xuống" if pitch > 0 else "ngẩng lên"
            alerts_parts.append(f"{direction.capitalize()} ({abs(pitch):.1f}°)")

        if alerts_parts:
            alert = "Quay đầu: " + ", ".join(alerts_parts)

        return {
            "yaw": round(yaw, 2),
            "pitch": round(pitch, 2),
            "roll": round(roll, 2),
            "alert": alert,
        }

    # ------------------------------------------------------------------
    # Phase 3: YOLOv8 Object Detection (PLACEHOLDER)
    # ------------------------------------------------------------------

    def _compute_overlap_ratio(self, box1, box2):
        x_left = max(box1[0], box2[0])
        y_top = max(box1[1], box2[1])
        x_right = min(box1[2], box2[2])
        y_bottom = min(box1[3], box2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

        # Sử dụng Intersection over Minimum Area (IoM) thay vì IoU
        # Tránh trường hợp 1 box quá nhỏ nằm trong 1 box rất to dẫn đến IoU quá thấp
        min_area = min(box1_area, box2_area)
        if min_area == 0:
            return 0.0
            
        return intersection_area / float(min_area)

    def detect_objects(self, frame: np.ndarray, confidence_threshold: float = None) -> dict | None:
        """
        Detect objects using dual YOLO models:
        - COCO model: phone, book, person, etc.
        - Custom model: calculator (and other custom-trained classes)
        Merges results from both models and resolves bounding box overlaps (IoU).
        """
        if self.object_detector is None and self.custom_detector is None:
            return None

        from backend.config import YOLO_CONFIDENCE_THRESHOLD, YOLO_RULES, YOLO_MAX_PERSONS

        coco_detections = []
        custom_detections = []
        person_count = 0

        # --- Model 1: COCO (yolov8n.pt) ---
        if self.object_detector is not None:
            results = self.object_detector(frame, verbose=False)
            for result in results:
                for box in result.boxes:
                    conf = float(box.conf[0])
                    conf_t = confidence_threshold if confidence_threshold is not None else YOLO_CONFIDENCE_THRESHOLD
                    if conf < conf_t:
                        continue
                    cls_id = int(box.cls[0])
                    class_name = self.object_detector.names[cls_id]

                    if class_name == "person":
                        person_count += 1

                    if class_name in YOLO_RULES:
                        coco_detections.append({
                            "class": class_name,
                            "confidence": round(conf, 4),
                            "level": YOLO_RULES[class_name]["level"],
                            "label": YOLO_RULES[class_name]["label"],
                            "source": "coco",
                            "bbox": box.xyxy[0].tolist()
                        })

        # --- Model 2: Custom (best.pt — calculator, etc.) ---
        if self.custom_detector is not None:
            custom_results = self.custom_detector(frame, verbose=False)
            for result in custom_results:
                for box in result.boxes:
                    conf = float(box.conf[0])
                    conf_t = confidence_threshold if confidence_threshold is not None else YOLO_CONFIDENCE_THRESHOLD
                    if conf < conf_t:
                        continue
                    cls_id = int(box.cls[0])
                    raw_class_name = self.custom_detector.names[cls_id]
                    
                    # Chuẩn hóa tên class: Nếu model train chứa từ "calculator" (ví dụ: "Calculator - V1...")
                    # thì quy về chuẩn "calculator" để ăn khớp với YOLO_RULES.
                    if "calculator" in raw_class_name.lower():
                        class_name = "calculator"
                    else:
                        class_name = raw_class_name

                    bbox_list = box.xyxy[0].tolist()

                    # Map custom class name vào YOLO_RULES nếu có
                    if class_name in YOLO_RULES:
                        custom_detections.append({
                            "class": class_name,
                            "confidence": round(conf, 4),
                            "level": YOLO_RULES[class_name]["level"],
                            "label": YOLO_RULES[class_name]["label"],
                            "source": "custom",
                            "bbox": bbox_list
                        })
                    else:
                        # Bỏ qua các class rác (như "---") từ custom model thay vì đánh đồng là CRITICAL
                        continue

        # --- Gộp chung tất cả detection lại để xử lý đè hộp (Unified NMS) ---
        all_detections = coco_detections + custom_detections
        
        # Priority mapping: số càng nhỏ ưu tiên càng cao.
        # Mục đích: Nếu 1 vật thể vừa bị nhận diện là 'cell phone' vừa là 'calculator',
        # ta tin tưởng nó là 'calculator' (vì custom model chuyên biệt hơn).
        def get_priority(class_name):
            if class_name == "calculator":
                return 1
            if class_name == "cell phone":
                return 2
            return 3

        # Sắp xếp theo ưu tiên (calculator lên đầu), sau đó theo độ tin cậy (cao xuống thấp)
        all_detections.sort(key=lambda x: (get_priority(x["class"]), -x["confidence"]))

        final_detections = []
        for det in all_detections:
            overlap = False
            for final_det in final_detections:
                # Tính độ đè nhau giữa box hiện tại và các box đã được chọn
                overlap_ratio = self._compute_overlap_ratio(det["bbox"], final_det["bbox"])
                # Nếu đè lên nhau >= 10% (Rất lỏng để bắt mọi trường hợp 2 model vẽ lệch)
                if overlap_ratio > 0.1:
                    overlap = True
                    break
            
            if not overlap:
                # Thêm vào danh sách cuối cùng nếu không bị đè với các box ưu tiên cao hơn
                final_detections.append(det)

        # Xóa bbox khỏi kết quả cuối cùng trước khi trả về frontend (để giảm payload nếu không cần)
        # Hoặc giữ lại nếu frontend cần vẽ bounding box (như hiện tại mình đang để lại bbox cho frontend)
        for det in final_detections:
            # Xóa bbox đi vì frontend hiện chỉ hiển thị danh sách (không vẽ box cho đồ vật)
            det.pop("bbox", None)

        return {
            "detections": final_detections,
            "person_count": person_count,
            "max_persons": YOLO_MAX_PERSONS,
        }

    # ------------------------------------------------------------------
    # Dynamic Enrollment (Phase 2 addition)
    # ------------------------------------------------------------------

    def add_anchor(self, mssv: str, name: str, image_bytes: bytes) -> dict:
        """
        Add a new student anchor dynamically.
        1. Decode image bytes → numpy array
        2. Extract ArcFace embedding
        3. Save to anchor_db + write file to data/anchor/
        Returns: {status, mssv, name, total_anchors}
        """
        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return {"status": "error", "message": "Cannot decode uploaded image."}

        # Extract face embedding
        faces = self.face_analyzer.get(img)

        if not faces:
            return {"status": "error", "message": "No face detected in uploaded image."}

        embedding = faces[0].embedding

        # Update RAM database
        self.anchor_db[mssv] = {
            "name": name,
            "embedding": embedding,
        }

        # Save file to disk for backup
        safe_name = name.replace(" ", "_")
        filename = f"{mssv}_{safe_name}.jpg"
        filepath = os.path.join(ANCHOR_DIR, filename)
        cv2.imwrite(filepath, img)

        logger.info(f"[Enrollment] Added {mssv} ({name}). Total anchors: {len(self.anchor_db)}")

        return {
            "status": "ok",
            "mssv": mssv,
            "name": name,
            "total_anchors": len(self.anchor_db),
        }
