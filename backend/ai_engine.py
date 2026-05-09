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
)

logger = logging.getLogger("anti_cheat.ai_engine")


class AIEngine:
    """Central AI processing unit. Loads models once at startup."""

    def __init__(self):
        self.face_analyzer = None    # insightface FaceAnalysis
        self.face_landmarker = None  # mediapipe FaceLandmarker
        self.object_detector = None  # ultralytics YOLO
        self.anchor_db: dict = {}    # {MSSV: {"name": str, "embedding": np.ndarray}}

    # ------------------------------------------------------------------
    # Phase 1: Model Loading
    # ------------------------------------------------------------------

    def load_models(self):
        """Load all 3 AI models into RAM. Called once at server startup."""
        self._load_arcface()
        self._load_mediapipe()
        self._load_yolo()

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
            logger.info("[YOLOv8] Model loaded successfully.")
        except Exception as e:
            logger.warning(f"[YOLOv8] Failed to load (non-blocking): {e}")

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
            }

        # 2. Tìm khuôn mặt to nhất (dựa trên diện tích bounding box)
        largest_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        
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
            }
        else:
            # Trạng thái 3: Sai người / Người lạ
            return {
                "status": "Unknown",
                "name": "Sai người",
                "similarity": round(sim, 4),
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

    def detect_objects(self, frame: np.ndarray) -> dict | None:
        """
        Detect forbidden and allowed objects using YOLOv8.
        """
        if self.object_detector is None:
            return None

        from backend.config import YOLO_CONFIDENCE_THRESHOLD, YOLO_FORBIDDEN_CLASSES, YOLO_ALLOWED_CLASSES

        results = self.object_detector(frame, verbose=False)
        detections = []
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                conf = float(box.conf[0])
                if conf < YOLO_CONFIDENCE_THRESHOLD:
                    continue
                
                cls_id = int(box.cls[0])
                class_name = self.object_detector.names[cls_id]
                
                if class_name in YOLO_FORBIDDEN_CLASSES or class_name in YOLO_ALLOWED_CLASSES:
                    detections.append({
                        "class": class_name,
                        "confidence": round(conf, 4)
                    })
        
        return {"detections": detections}

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
