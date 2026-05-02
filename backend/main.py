"""
main.py — FastAPI application entry point.
Loads AI models at startup via lifespan, serves API + static frontend.
"""
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai_engine import AIEngine
from backend.config import ANCHOR_DIR, LOG_DIR
from backend.schemas import FrameRequest, FrameResponse, IdentityResult

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anti_cheat.main")

# --- Global AI Engine ---
engine = AIEngine()


# --- Lifespan: Load models once at startup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("STARTING Anti-Cheat System...")
    logger.info("=" * 60)

    # Load all 3 AI models into RAM
    engine.load_models()

    # Load anchor face embeddings from data/anchor/
    engine.load_anchors(ANCHOR_DIR)

    logger.info(f"Anchors loaded: {len(engine.anchor_db)}")
    logger.info("System READY. Waiting for connections...")
    logger.info("=" * 60)

    yield  # App runs here

    logger.info("Shutting down Anti-Cheat System.")


# --- FastAPI App ---
app = FastAPI(
    title="Anti-Cheat Webcam System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for localhost development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check — verify server and models are ready."""
    return {
        "status": "ok",
        "anchors_loaded": len(engine.anchor_db),
        "models": {
            "arcface": engine.face_analyzer is not None,
            "mediapipe": engine.face_landmarker is not None,
            "yolov8": engine.object_detector is not None,
        },
    }


@app.post("/api/process_frame", response_model=FrameResponse)
async def process_frame(request: FrameRequest):
    """
    Main anti-cheat endpoint.
    Receives base64 JPEG + MSSV, runs AI pipeline, returns alerts.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Decode base64 image → numpy array
    try:
        # Strip data URL prefix if present
        image_data = request.frame
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise ValueError("Failed to decode image")
    except Exception as e:
        return FrameResponse(
            identity=IdentityResult(
                verified=False, similarity=0.0,
                name="Error", message=f"Image decode error: {str(e)}",
            ),
            alerts=[f"❌ ERROR: {str(e)}"],
            timestamp=timestamp,
        )

    # 2. Run AI pipeline
    identity_result = engine.verify_identity(frame)
    head_pose_result = engine.analyze_head_pose(frame)    # Returns None (placeholder)
    objects_result = engine.detect_objects(frame)          # Returns None (placeholder)

    # 3. Build alerts list
    alerts = _build_alerts(identity_result, head_pose_result, objects_result)

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
    Dynamic Face Enrollment — upload student photo via web form.
    Extracts ArcFace embedding, updates RAM + saves file to data/anchor/.
    """
    image_bytes = await photo.read()

    if not image_bytes:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Empty file uploaded."},
        )

    result = engine.add_anchor(mssv, name, image_bytes)

    if result["status"] == "error":
        return JSONResponse(status_code=400, content=result)

    return result


# ------------------------------------------------------------------
# Alert Builder
# ------------------------------------------------------------------

def _build_alerts(identity: dict, head_pose: dict | None, objects: dict | None) -> list[str]:
    """Compile human-readable alert strings from AI results."""
    alerts = []

    # Identity alerts
    if identity["status"] == "Match":
        alerts.append(f"✅ MATCH: {identity['name']} (similarity: {identity['similarity']})")
    elif identity["status"] == "Unknown":
        alerts.append(f"⚠️ NGƯỜI LẠ (similarity: {identity['similarity']})")
    else:
        alerts.append(f"⚠️ KHÔNG CÓ KHUÔN MẶT")

    # Head pose alerts (placeholder — will add when implemented)
    if head_pose:
        pass  # TODO: Parse head_pose dict and generate alerts

    # Object detection alerts (placeholder — will add when implemented)
    if objects:
        pass  # TODO: Parse objects dict and generate alerts

    return alerts


# ------------------------------------------------------------------
# Mount Frontend Static Files
# ------------------------------------------------------------------
import os
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
