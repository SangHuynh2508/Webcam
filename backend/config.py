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

# --- YOLOv8 Object Detection ---
YOLO_MODEL_PATH = "yolov8n.pt"
CUSTOM_YOLO_MODEL_PATH = "best.pt"  # Custom-trained: calculator detection
YOLO_CONFIDENCE_THRESHOLD = 0.65  # Tăng ngưỡng lên 0.65 để giảm nhận diện nhầm (ảo giác)

# Quy tắc phân loại vật thể trong phòng thi
# Level: CRITICAL (gian lận trực tiếp), WARNING (khả nghi), OK (hợp lệ)
YOLO_RULES = {
    # === VẬT CẤM — Gian lận trực tiếp ===
    "cell phone":   {"level": "CRITICAL", "label": "Điện thoại"},
    "book":         {"level": "CRITICAL", "label": "Sách/Tài liệu"},
    "remote":       {"level": "CRITICAL", "label": "Thiết bị điều khiển từ xa"},

    # === CẢNH BÁO — Khả nghi, cần giám sát ===
    "backpack":     {"level": "WARNING", "label": "Ba lô trên bàn"},
    "handbag":      {"level": "WARNING", "label": "Túi xách trên bàn"},
    "suitcase":     {"level": "WARNING", "label": "Vali/cặp trên bàn"},
    "clock":        {"level": "WARNING", "label": "Đồng hồ (có thể là smartwatch)"},
    "scissors":     {"level": "WARNING", "label": "Kéo/vật sắc nhọn"},

    # === HỢP LỆ — Cho phép trong phòng thi ===
    "laptop":       {"level": "OK", "label": "Laptop"},
    "keyboard":     {"level": "OK", "label": "Bàn phím"},
    "mouse":        {"level": "OK", "label": "Chuột"},
    "tv":           {"level": "OK", "label": "Màn hình"},
    "cup":          {"level": "OK", "label": "Cốc/ly"},
    "bottle":       {"level": "OK", "label": "Chai nước"},
    "calculator":   {"level": "OK", "label": "Máy tính Casio"},  # Custom model
}

# Số người tối đa cho phép trong khung hình (>1 = có người hỗ trợ)
YOLO_MAX_PERSONS = 1

# --- Webcam Capture ---
CAPTURE_INTERVAL_MS = 2000  # Client-side capture interval
JPEG_QUALITY = 0.7          # Canvas toDataURL quality

# --- Server ---
HOST = "0.0.0.0"
PORT = 8000
