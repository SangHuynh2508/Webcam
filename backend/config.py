"""
config.py — Thresholds & Constants for Anti-Cheat System
"""
import os

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCHOR_DIR = os.path.join(BASE_DIR, "data", "anchor")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# --- ArcFace (InsightFace) ---
FACE_DETECTION_MODEL = "buffalo_l"  # ArcFace ResNet100 bundle
FACE_SIMILARITY_THRESHOLD = 0.55   # Cosine similarity >= this → Match

# --- MediaPipe Head Pose (Placeholder thresholds) ---
HEAD_YAW_THRESHOLD = 30.0    # degrees — liếc trái/phải
HEAD_PITCH_THRESHOLD = 25.0  # degrees — cúi/ngẩng

# --- YOLOv8 Object Detection (Thresholds) ---
YOLO_MODEL_PATH = "yolov8n.pt"
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_FORBIDDEN_CLASSES = ["cell phone", "book"]
YOLO_ALLOWED_CLASSES = ["laptop"]

# --- Webcam Capture ---
CAPTURE_INTERVAL_MS = 2000  # Client-side capture interval
JPEG_QUALITY = 0.7          # Canvas toDataURL quality

# --- Server ---
HOST = "0.0.0.0"
PORT = 8000
