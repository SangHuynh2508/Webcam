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
        """Load MediaPipe Face Landmarker for head pose estimation."""
        try:
            import mediapipe as mp
            self.face_landmarker = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
            logger.info("[MediaPipe] FaceMesh loaded successfully.")
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

    # ------------------------------------------------------------------
    # Phase 3: ArcFace Identity Verification (FULLY IMPLEMENTED)
    # ------------------------------------------------------------------

    def verify_identity(self, frame: np.ndarray, mssv: str) -> dict:
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
        if sim > FACE_SIMILARITY_THRESHOLD:
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
    # Phase 3: MediaPipe Head Pose (PLACEHOLDER)
    # ------------------------------------------------------------------

    def analyze_head_pose(self, frame: np.ndarray) -> dict | None:
        """
        Analyze head orientation (Yaw, Pitch, Roll) using MediaPipe.
        TODO: Implement in next iteration after ArcFace pipeline is stable.
        """
        # PLACEHOLDER — will return {yaw, pitch, roll, alert} when implemented
        return None

    # ------------------------------------------------------------------
    # Phase 3: YOLOv8 Object Detection (PLACEHOLDER)
    # ------------------------------------------------------------------

    def _compute_iou(self, box1, box2):
        x_left = max(box1[0], box2[0])
        y_top = max(box1[1], box2[1])
        x_right = min(box1[2], box2[2])
        y_bottom = min(box1[3], box2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

        return intersection_area / float(box1_area + box2_area - intersection_area)

    def detect_objects(self, frame: np.ndarray) -> dict | None:
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
                    if conf < YOLO_CONFIDENCE_THRESHOLD:
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
                    if conf < YOLO_CONFIDENCE_THRESHOLD:
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

        # --- Resolve Overlaps (NMS across models) ---
        # If COCO detects a cell phone and Custom detects a calculator at the same spot,
        # we trust the Custom model more and drop the COCO detection.
        final_detections = []
        for c_det in coco_detections:
            overlap = False
            for cust_det in custom_detections:
                iou = self._compute_iou(c_det["bbox"], cust_det["bbox"])
                # Hạ IoU xuống 0.1 để bắt độ trùng lấp dễ hơn (đề phòng 2 model vẽ box lệch nhau)
                if iou > 0.1:  
                    overlap = True
                    break
            
            if not overlap:
                c_det.pop("bbox", None)
                final_detections.append(c_det)
                
        for cust_det in custom_detections:
            cust_det.pop("bbox", None)
            final_detections.append(cust_det)

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
