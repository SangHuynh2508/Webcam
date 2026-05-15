"""
main.py — FastAPI application entry point.
Loads AI models at startup via lifespan, serves API + static frontend.
Phase 5: Integrated CSV logging for audit trail.
"""
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai_engine import AIEngine
from backend.config import ANCHOR_DIR, LOG_DIR
from backend.schemas import FrameRequest, FrameResponse, IdentityResult
from backend.csv_logger import CSVLogger

# --- Cấu hình Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anti_cheat.main")

# --- AI Engine Toàn cục ---
engine = AIEngine()

# --- CSV Logger cho Phase 5: Ghi Log ---
csv_logger = CSVLogger(LOG_DIR)


# --- Lifespan: Load models lần duy nhất khi khởi động ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("🚀 KHỞI CHẠY Hệ thống Anti-Cheat...")
    logger.info("=" * 60)

    # Load toàn bộ 3 model AI vào RAM
    engine.load_models()

    # Load các embedding khuôn mặt tham khảo từ data/anchor/
    engine.load_anchors(ANCHOR_DIR)

    logger.info(f"✅ Đã load anchors: {len(engine.anchor_db)}")
    logger.info("✨ Hệ thống SẴN SÀNG. Chờ kết nối...")
    logger.info("=" * 60)

    yield  # Chạy ứng dụng ở đây

    logger.info("🛑 Tắt Hệ thống Anti-Cheat.")


# --- FastAPI App ---
app = FastAPI(
    title="Hệ thống Anti-Cheat Webcam",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS cho phát triển localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Các Endpoints API
# ------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Kiểm tra sức khỏe — xác minh server và model đã sẵn sàng."""
    return {
        "status": "ok",
        "anchors_loaded": len(engine.anchor_db),
        "models": {
            "arcface": engine.face_analyzer is not None,
            "mediapipe": engine.face_landmarker is not None,
            "yolov8_coco": engine.object_detector is not None,
            "yolov8_custom": engine.custom_detector is not None,
        },
    }


@app.post("/api/process_frame", response_model=FrameResponse)
async def process_frame(request: FrameRequest):
    """
    Endpoint chính cho anti-cheat.
    Nhận ảnh JPEG base64 + MSSV, chạy AI pipeline, trả về cảnh báo.
    Phase 5: Kết quả được ghi tự động vào CSV để tạo audit trail.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Giải mã ảnh base64 → numpy array
    try:
        # Loại bỏ tiền tố data URL nếu có
        image_data = request.frame
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise ValueError("❌ Lỗi giải mã ảnh")
    except Exception as e:
        return FrameResponse(
            identity=IdentityResult(
                status="Error",
                name="Error",
                similarity=0.0,
            ),
            alerts=[f"❌ LỖI: {str(e)}"],
            timestamp=timestamp,
        )

    # 2. Run AI pipeline
    identity_result = engine.verify_identity(frame, request.mssv)
    head_pose_result = engine.analyze_head_pose(frame)    # Returns None (placeholder)
    objects_result = engine.detect_objects(frame)          # Trả về None (placeholder)

    # 3. Xây dựng danh sách cảnh báo
    alerts = _build_alerts(identity_result, head_pose_result, objects_result)

    # 4. Ghi vào CSV (Phase 5: Ghi log tự động)
    csv_data = {
        "timestamp": timestamp,
        "mssv": request.mssv,
        "name": identity_result.get("name", "Không xác định"),
        "identity_status": identity_result.get("status", "Không xác định"),
        "similarity_score": identity_result.get("similarity", 0.0),
        "alerts": alerts,
    }
    csv_logger.log_frame(csv_data)

    return FrameResponse(
        identity=IdentityResult(**identity_result),
        head_pose=head_pose_result,
        objects=objects_result,
        alerts=alerts,
        timestamp=timestamp,
    )


@app.post("/api/add_student")
async def add_student(
    mssv: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(...),
):
    """
    Đăng ký động khuôn mặt sinh viên — tải ảnh qua form web.
    Trích xuất embedding ArcFace, cập nhật RAM + lưu file vào data/anchor/.
    """
    image_bytes = await photo.read()

    if not image_bytes:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "❌ File ảnh trống."},
        )

    result = engine.add_anchor(mssv, name, image_bytes)

    if result["status"] == "error":
        return JSONResponse(status_code=400, content=result)

    return result


# ------------------------------------------------------------------
# Phase 5: Endpoints Ghi Log & Audit Trail
# ------------------------------------------------------------------

@app.get("/api/logs")
async def get_logs(
    session_id: str = Query(None),
    limit: int = Query(100),
):
    """
    Lấy dữ liệu đã ghi log từ file CSV.
    
    Tham số Query:
        session_id: ID phiên thi (mặc định: ngày hôm nay YYYYMMDD)
        limit: Số dòng tối đa trả về (mặc định: 100)
    """
    try:
        data = csv_logger.get_session_data(session_id, limit)
        
        return {
            "status": "ok",
            "session_id": session_id or datetime.now().strftime("%Y%m%d"),
            "total_rows": len(data),
            "data": data,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"❌ Lỗi: {str(e)}"},
        )


@app.get("/api/logs/stats")
async def get_logs_stats(session_id: str = Query(None)):
    """
    Lấy thống kê của một phiên thi cụ thể.
    
    Tham số Query:
        session_id: ID phiên thi (mặc định: ngày hôm nay YYYYMMDD)
    """
    try:
        stats = csv_logger.get_session_stats(session_id)
        
        return {
            "status": "ok",
            "session_id": session_id or datetime.now().strftime("%Y%m%d"),
            "stats": stats,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"❌ Lỗi: {str(e)}"},
        )


@app.get("/api/logs/sessions")
async def list_sessions():
    """
    Liệt kê tất cả các phiên thi có sẵn (file CSV).
    """
    try:
        sessions = csv_logger.list_sessions()
        
        return {
            "status": "ok",
            "sessions": sessions,
            "total_sessions": len(sessions),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"❌ Lỗi: {str(e)}"},
        )


# ------------------------------------------------------------------
# Xây dựng Cảnh báo
# ------------------------------------------------------------------

def _build_alerts(identity: dict, head_pose: dict | None, objects: dict | None) -> list[str]:
    """Compile human-readable alert strings from AI results."""
    alerts = []

    # Identity alerts
    if identity["status"] == "Match":
        alerts.append(f"✅ ĐÚNG NGƯỜI: {identity['name']} (sim: {identity['similarity']})")
    elif identity["status"] == "Unknown":
        alerts.append(f"⚠️ SAI NGƯỜI: Phát hiện gian lận (sim: {identity['similarity']})")
    elif identity["status"] == "Error":
        alerts.append(f"❌ LỖI: MSSV chưa được đăng ký dữ liệu khuôn mặt")
    else:
        alerts.append(f"⚠️ KHÔNG CÓ KHUÔN MẶT")

    # Cảnh báo head pose (placeholder — sẽ thêm khi triển khai)
    if head_pose:
        pass  # TODO: Phân tích head_pose dict và tạo cảnh báo

    # Cảnh báo phát hiện vật thể (đa tầng)
    if objects:
        # Đếm người — phát hiện thi hộ
        person_count = objects.get("person_count", 0)
        max_persons = objects.get("max_persons", 1)
        if person_count > max_persons:
            alerts.append(
                f"🚨 CRITICAL: Phát hiện {person_count} người trong khung hình!"
            )

        # Phân loại vật thể theo mức độ
        for det in objects.get("detections", []):
            level = det.get("level", "OK")
            label = det.get("label", det["class"])
            conf = det["confidence"]

            if level == "CRITICAL":
                alerts.append(f"🚨 GIAN LẬN: {label} ({conf:.2f})")
            elif level == "WARNING":
                alerts.append(f"⚠️ CẢNH BÁO: {label} ({conf:.2f})")
            elif level == "OK":
                alerts.append(f"✅ HỢP LỆ: {label} ({conf:.2f})")

    return alerts


# ------------------------------------------------------------------
# Gắn File Tĩnh Frontend
# ------------------------------------------------------------------
import os
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
