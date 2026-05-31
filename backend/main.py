"""
main.py — FastAPI application entry point.
Integrates MongoDB database with authentication, role-based access control,
exam room division, real-time live session monitoring, violation escalation warnings,
and visual audit screenshot captures.
"""
import base64
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile, Query, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.ai_engine import AIEngine
from backend.config import ANCHOR_DIR, LOG_DIR
from backend.database import get_db
from backend.database.setup import run_setup
from backend.auth import (
    create_access_token,
    get_current_user,
    require_role,
)
from backend.schemas import (
    FrameRequest,
    FrameResponse,
    IdentityResult,
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    RoomCreate,
    RoomUpdate,
    RoomResponse,
    RoomStudentEnroll,
    ExamSessionStart,
    AIConfigUpdate,
    AIConfigResponse,
)
from backend.csv_logger import CSVLogger

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anti_cheat.main")

# --- Global AI Engine ---
engine = AIEngine()

# --- Legacy CSV Logger for Backward Compatibility ---
csv_logger = CSVLogger(LOG_DIR)


# --- Lifespan: Startup & Shutdown events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("🚀 KHỞI CHẠY Hệ thống Anti-Cheat tích hợp Database MongoDB...")
    logger.info("=" * 60)

    # Automatically set up MongoDB validations and indexes (drop_existing=False to preserve data)
    setup_ok = run_setup(drop_existing=False)
    if setup_ok:
        logger.info("✅ Đã thiết lập xong cấu trúc validation và indexes MongoDB.")
    else:
        logger.warning("Không thể kết nối hoặc thiết lập MongoDB. Chạy ở chế độ giới hạn.")
    
    # Load all 3 AI models into RAM
    engine.load_models()

    # Load legacy anchors from data/anchor/ for fallback
    engine.load_anchors(ANCHOR_DIR)

    logger.info(f"Đã nạp xong models và {len(engine.anchor_db)} anchors tham chiếu.")
    logger.info("Hệ thống SẴN SÀNG. Chờ kết nối...")
    logger.info("=" * 60)

    yield  # Application runs here

    logger.info("Tắt Hệ thống Anti-Cheat.")


# --- FastAPI App ---
app = FastAPI(
    title="Hệ thống Anti-Cheat Webcam & Database",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# 1. AUTHENTICATION & USER MANAGEMENT API
# ------------------------------------------------------------------

@app.post("/api/auth/register", response_model=UserResponse)
async def register(user_data: UserRegister, db = Depends(get_db)):
    """Registers a new user in the system."""
    try:
        new_user = await db.register_user(
            username=user_data.username,
            password_plain=user_data.password,
            role=user_data.role,
            full_name=user_data.full_name,
            mssv=user_data.mssv
        )
        return new_user
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db = Depends(get_db)):
    """Logs in a user and returns a JWT access token."""
    user = await db.authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác."
        )

    access_token = create_access_token(data={"sub": user["username"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Retrieves current user details using access token."""
    return current_user


# ------------------------------------------------------------------
# 2. EXAM ROOM DIVISION & CRUD API
# ------------------------------------------------------------------

@app.post("/api/rooms/create", response_model=RoomResponse)
async def create_room(
    room_data: RoomCreate,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Creates a new exam room. Restricted to teachers and admins."""
    try:
        new_room = await db.create_room(
            room_code=room_data.room_code,
            title=room_data.title,
            description=room_data.description or "",
            teacher_id=current_user["id"]
        )
        
        # Auto-enroll all existing students for testing purposes
        # So students immediately see the newly created room on their dashboard
        students = await db.users.find({"role": "student"}).to_list(length=None)
        for student in students:
            try:
                # Resolve anchor photo if exists
                photo_path = None
                anchor_filename = f"{student['mssv']}_HuynhMinhSang.jpg" if student.get('mssv') == "2380601889" else None
                if anchor_filename and os.path.exists(os.path.join(ANCHOR_DIR, anchor_filename)):
                    photo_path = os.path.join(ANCHOR_DIR, anchor_filename)
                
                await db.enroll_student(new_room["room_code"], student["mssv"], face_image_path=photo_path)
            except Exception:
                pass # Skip if they cannot be enrolled (e.g., missing mssv)
                
        return new_room
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@app.get("/api/rooms/teacher-rooms", response_model=List[RoomResponse])
async def get_teacher_rooms(
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Retrieves all exam rooms created by the current teacher."""
    rooms = await db.get_rooms_by_teacher(current_user["id"])
    return rooms


@app.get("/api/rooms/student-rooms", response_model=List[RoomResponse])
async def get_student_rooms(
    current_user: dict = Depends(require_role(["student"])),
    db = Depends(get_db)
):
    """Retrieves all exam rooms the student is enrolled in."""
    rooms = await db.get_rooms_by_student(current_user["id"])
    return rooms


@app.put("/api/rooms/{room_code}", response_model=RoomResponse)
async def update_room(
    room_code: str,
    room_data: RoomUpdate,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Updates an exam room details."""
    room = await db.update_room(room_code, room_data.title, room_data.description or "")
    if not room:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")
    return room


@app.delete("/api/rooms/{room_code}")
async def delete_room(
    room_code: str,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Deletes an exam room and cascades deleting sessions and logs."""
    success = await db.delete_room(room_code)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")
    return {"status": "ok", "message": "Đã xóa phòng thi thành công."}


@app.post("/api/rooms/enroll")
async def enroll_student(
    enroll_data: RoomStudentEnroll,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Enrolls a student into an exam room using their MSSV."""
    # Find student to check if photo path can be resolved
    student = await db.users.find_one({"mssv": enroll_data.mssv, "role": "student"})
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên có MSSV này.")

    photo_path = None
    anchor_filename = f"{student['mssv']}_HuynhMinhSang.jpg" if student['mssv'] == "2380601889" else None
    if anchor_filename and os.path.exists(os.path.join(ANCHOR_DIR, anchor_filename)):
        photo_path = os.path.join(ANCHOR_DIR, anchor_filename)

    try:
        res = await db.enroll_student(enroll_data.room_code, enroll_data.mssv, face_image_path=photo_path)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/rooms/{room_code}/students/{mssv}")
async def unenroll_student(
    room_code: str,
    mssv: str,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Unenrolls/removes a student from an exam room."""
    try:
        success = await db.unenroll_student(room_code, mssv)
        if not success:
            raise HTTPException(status_code=404, detail="Không thể hủy ghi danh sinh viên.")
        return {"status": "ok", "message": f"Đã hủy ghi danh sinh viên {mssv} khỏi phòng {room_code}."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/rooms/{room_code}/students")
async def get_room_students(
    room_code: str,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Retrieves all students enrolled in a specific room."""
    try:
        result = await db.get_room_students(room_code)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# 3. EXAM SESSION FLOW & REAL-TIME LOGGING API
# ------------------------------------------------------------------

@app.post("/api/exam/start")
async def start_exam(
    payload: ExamSessionStart,
    current_user: dict = Depends(require_role(["student"])),
    db = Depends(get_db)
):
    """Starts a student's active exam session and dynamically loads reference faces for this room."""
    try:
        # 1. Start new session (internally terminates old unsubmitted sessions)
        new_session = await db.start_exam_session(payload.room_code, current_user["id"])
        
        # 2. Get anchors for the room
        anchors = await db.get_room_anchors(payload.room_code)
        
        # 3. Check for any missing face embeddings but possessing a valid face photo path
        for a in anchors:
            if a["embedding"] is None and a["face_image_path"] and os.path.exists(a["face_image_path"]):
                img = cv2.imread(a["face_image_path"])
                if img is not None:
                    faces = engine.face_analyzer.get(img)
                    if faces:
                        emb = faces[0].embedding.tolist()
                        await db.update_student_face_data(a["mssv"], emb)
                        a["embedding"] = emb
        
        # 4. Load resolved anchors into AIEngine
        engine.load_room_anchors(anchors)

        # Retrieve room details
        room = await db.get_room_by_code(payload.room_code)

        return {
            "status": "ok",
            "message": f"Bắt đầu phiên làm bài tại phòng {room['title'] if room else payload.room_code}.",
            "session_id": new_session["id"],
            "room_title": room["title"] if room else payload.room_code
        }
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/exam/submit")
async def submit_exam(
    current_user: dict = Depends(require_role(["student"])),
    db = Depends(get_db)
):
    """Ends the student's currently active exam session."""
    success = await db.submit_exam_session(current_user["id"])
    if not success:
        raise HTTPException(status_code=400, detail="Không tìm thấy phiên làm bài đang chạy.")

    # Reload fallback local anchors
    engine.anchor_db = {}
    engine.load_anchors(ANCHOR_DIR)

    return {"status": "ok", "message": "Đã nộp bài và dừng phiên giám sát thành công."}


@app.get("/api/rooms/{room_code}/status")
async def get_room_live_status(
    room_code: str,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """
    Retrieves real-time status of all student sessions in a room (Live Monitor Dashboard).
    """
    try:
        res = await db.get_room_live_status(room_code)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/logs/violations")
async def get_violation_logs(
    room_code: Optional[str] = Query(None),
    mssv: Optional[str] = Query(None),
    limit: int = Query(50),
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """
    Queries violation logs with filters. Supports premium visual screenshots.
    """
    res = await db.get_violation_logs(room_code, mssv, limit)
    return res


@app.get("/api/violations/image/{log_id}")
async def get_violation_image(
    log_id: str,
    db = Depends(get_db)
):
    """Serves the cheating visual screenshot for audit purposes."""
    log = await db.get_violation_log_by_id(log_id)
    if not log or not log.get("frame_image_path") or not os.path.exists(log["frame_image_path"]):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh bằng chứng.")

    return FileResponse(log["frame_image_path"])


# ------------------------------------------------------------------
# 4. SYSTEM AI CONFIGURATION API
# ------------------------------------------------------------------

@app.get("/api/settings", response_model=AIConfigResponse)
async def get_settings(
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Gets the global system thresholds and violation limits configuration."""
    settings = await db.get_system_settings()
    return settings


@app.put("/api/settings", response_model=AIConfigResponse)
async def update_settings(
    payload: AIConfigUpdate,
    current_user: dict = Depends(require_role(["admin", "teacher"])),
    db = Depends(get_db)
):
    """Updates the global system thresholds configuration dynamically."""
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    settings = await db.update_system_settings(updates)
    return settings


# ------------------------------------------------------------------
# 5. FRAME PROCESSING API (INTEGRATING MongoDB DATABASE LOGGING)
# ------------------------------------------------------------------

@app.post("/api/process_frame", response_model=FrameResponse)
async def process_frame(request: FrameRequest, db = Depends(get_db)):
    """
    Main real-time anti-cheat AI processing engine.
    Receives JPEG base64 and student ID (MSSV), performs AI analytics,
    saves violations in MongoDB database, escalates warning count, and captures audit screenshots.
    """
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Decode base64 frame -> numpy image
    try:
        image_data = request.frame
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        img_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise ValueError("Lỗi giải mã ảnh")
    except Exception as e:
        return FrameResponse(
            identity=IdentityResult(status="Error", name="Error", similarity=0.0),
            alerts=[f"LỖI GIẢI MÃ: {str(e)}"],
            timestamp=timestamp_str,
        )

    # 2. Get dynamic settings from MongoDB
    sys_settings = await db.get_system_settings()
    face_threshold = sys_settings.get("face_similarity_threshold", 0.55)
    yolo_threshold = sys_settings.get("yolo_confidence_threshold", 0.65)
    head_yaw_threshold = sys_settings.get("head_yaw_threshold", 30.0)
    head_pitch_threshold = sys_settings.get("head_pitch_threshold", 25.0)

    # 3. Query Student & Active Exam Session
    student = await db.users.find_one({"mssv": request.mssv, "role": "student"})
    active_session = None
    if student:
        active_session = await db.sessions.find_one(
            {"student_id": student["_id"], "ended_at": None},
            sort=[("started_at", -1)]
        )

    # 4. Run AI Analytics Pipeline
    identity_result = engine.verify_identity(frame, request.mssv, threshold=face_threshold)
    
    # Optimization: if identity is Error, skip head pose and object detection to save CPU
    if identity_result["status"] == "Error":
        head_pose_result = None
        objects_result = None
    else:
        head_pose_result = engine.analyze_head_pose(frame, yaw_threshold=head_yaw_threshold, pitch_threshold=head_pitch_threshold)
        objects_result = engine.detect_objects(frame, confidence_threshold=yolo_threshold)

    # 5. Compile Human-Readable Alerts
    alerts = _build_alerts(identity_result, head_pose_result, objects_result)

    # Track vi phạm tích lũy để trả về frontend
    session_violation_count = 0

    # 6. Database Logging & Warnings Escalation (If student has an active session)
    if active_session and student:
        violations_to_log = []

        # A. Identity Violation (Wrong identity)
        if identity_result["status"] == "Unknown":
            violations_to_log.append({
                "type": "unknown_identity",
                "severity": "CRITICAL",
                "score": identity_result["similarity"],
                "details": f"Phát hiện sai người thi. Nhận diện: {identity_result['name']} (sim: {identity_result['similarity']})"
            })
            
        # B. Absence Violation (No face)
        elif identity_result["status"] == "No Face":
            violations_to_log.append({
                "type": "no_face",
                "severity": "WARNING",
                "score": 0.0,
                "details": "Không phát hiện khuôn mặt sinh viên trước camera."
            })

        # C. Head Pose Violation (MediaPipe)
        if head_pose_result and head_pose_result.get("alert"):
            violations_to_log.append({
                "type": "head_pose_violation",
                "severity": "WARNING",
                "score": max(abs(head_pose_result.get("yaw", 0)), abs(head_pose_result.get("pitch", 0))),
                "details": f"Vi phạm tư thế đầu: {head_pose_result['alert']} (Yaw: {head_pose_result['yaw']}°, Pitch: {head_pose_result['pitch']}°)"
            })

        # D. Banned Objects & Helper Detection (YOLOv8)
        if objects_result:
            person_count = objects_result.get("person_count", 0)
            if person_count > objects_result.get("max_persons", 1):
                violations_to_log.append({
                    "type": "multiple_persons",
                    "severity": "CRITICAL",
                    "score": 0.0,
                    "details": f"Phát hiện có {person_count} người trong khung hình giám sát."
                })

            for det in objects_result.get("detections", []):
                level = det.get("level", "OK")
                label = det.get("label", det["class"])
                conf = det["confidence"]
                
                if level in ["CRITICAL", "WARNING"]:
                    violations_to_log.append({
                        "type": f"banned_object_{det['class']}",
                        "severity": level,
                        "score": conf,
                        "details": f"Phát hiện vật thể cấm: {label} ({conf:.2f})"
                    })

        # Process violations
        if violations_to_log:
            # Capture premium visual audit screenshot
            violation_dir = os.path.join(LOG_DIR, "violations")
            os.makedirs(violation_dir, exist_ok=True)
            
            frame_filename = f"sess_{str(active_session['_id'])}_{int(datetime.now().timestamp())}.jpg"
            frame_path = os.path.join(violation_dir, frame_filename)
            cv2.imwrite(frame_path, frame)

            # Record each violation log and escalate warning count
            for v in violations_to_log:
                await db.log_violation(
                    session_id=active_session["_id"],
                    room_id=active_session["room_id"],
                    student_id=student["_id"],
                    violation_type=v["type"],
                    severity=v["severity"],
                    similarity_score=v["score"],
                    details=v["details"],
                    frame_image_path=frame_path
                )

            # Fetch updated session count
            updated_session = await db.sessions.find_one({"_id": active_session["_id"]})
            if updated_session:
                violation_count = updated_session.get("violation_count", 0)
                session_violation_count = violation_count
                status_str = updated_session.get("status", "NORMAL")
                alerts.append(f"HỆ THỐNG: Cảnh báo vi phạm tích lũy! Lần: {violation_count} (Trạng thái: {status_str})")
        else:
            # Lấy violation_count hiện tại dù không có vi phạm mới
            session_violation_count = active_session.get("violation_count", 0)

    # 7. Legacy CSV Logger fallback
    csv_data = {
        "timestamp": timestamp_str,
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
        timestamp=timestamp_str,
        violation_count=session_violation_count,
    )


# ------------------------------------------------------------------
# 6. DYNAMIC ENROLLMENT & FALLBACK ROUTING
# ------------------------------------------------------------------

@app.post("/api/add_student")
async def add_student(
    mssv: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(...),
    db = Depends(get_db)
):
    """
    Registers a student's face dynamically.
    Creates / updates the User account, extracts ArcFace face embedding,
    saves the reference photo, and caches it in the MongoDB database.
    """
    image_bytes = await photo.read()
    if not image_bytes:
        return JSONResponse(status_code=400, content={"status": "error", "message": "File ảnh trống."})

    # Call AI engine dynamic enrollment (updates in-memory anchors)
    result = engine.add_anchor(mssv, name, image_bytes)
    if result["status"] == "error":
        return JSONResponse(status_code=400, content=result)

    # Additionally, check and create User account in Database
    student = await db.users.find_one({"mssv": mssv})
    if not student:
        username = f"sv_{mssv}"
        student = await db.register_user(
            username=username,
            password_plain="student123",
            role="student",
            full_name=name,
            mssv=mssv
        )

    # Save to RoomStudent database (Enroll in first exam room or all active exam rooms)
    saved_photo_name = f"{mssv}_{name.replace(' ', '_')}.jpg"
    saved_photo_path = os.path.join(ANCHOR_DIR, saved_photo_name)
    
    # Serialize embedding float list
    embedding_val = engine.anchor_db[mssv]["embedding"]
    embedding_list = embedding_val.tolist()

    cursor = db.rooms.find({})
    async for room in cursor:
        await db.enroll_student(room["room_code"], mssv, face_image_path=saved_photo_path)
        await db.update_student_face_data(mssv, embedding_list, face_image_path=saved_photo_path)
        
    return result


# --- Legacy csv stats endpoints (for compatibility) ---

@app.get("/api/logs")
async def get_logs_legacy(session_id: str = Query(None), limit: int = Query(100)):
    try:
        data = csv_logger.get_session_data(session_id, limit)
        return {"status": "ok", "session_id": session_id or datetime.now().strftime("%Y%m%d"), "total_rows": len(data), "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Lỗi: {str(e)}"})


@app.get("/api/logs/stats")
async def get_logs_stats_legacy(session_id: str = Query(None)):
    try:
        stats = csv_logger.get_session_stats(session_id)
        return {"status": "ok", "session_id": session_id or datetime.now().strftime("%Y%m%d"), "stats": stats}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Lỗi: {str(e)}"})


@app.get("/api/logs/sessions")
async def list_sessions_legacy():
    try:
        sessions = csv_logger.list_sessions()
        return {"status": "ok", "sessions": sessions, "total_sessions": len(sessions)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Lỗi: {str(e)}"})


# ------------------------------------------------------------------
# 7. SYSTEM ALERTS COMPILATION
# ------------------------------------------------------------------

def _build_alerts(identity: dict, head_pose: dict | None, objects: dict | None) -> list[str]:
    """Compiles human-readable alert strings from model predictions."""
    alerts = []

    # A. Face matching identity alert
    if identity["status"] == "Match":
        alerts.append(f"ĐÚNG NGƯỜI: {identity['name']} (sim: {identity['similarity']})")
    elif identity["status"] == "Unknown":
        alerts.append(f"SAI NGƯỜI: Phát hiện gian lận (sim: {identity['similarity']})")
    elif identity["status"] == "Error":
        alerts.append("LỖI: MSSV chưa được đăng ký khuôn mặt")
    else:
        alerts.append("KHÔNG CÓ KHUÔN MẶT")

    # B. MediaPipe Head pose alerts
    if head_pose:
        yaw = head_pose.get("yaw", 0)
        pitch = head_pose.get("pitch", 0)
        head_alert = head_pose.get("alert")

        if head_alert:
            alerts.append(f"QUAY ĐẦU: {head_alert}")
        else:
            alerts.append(f"TƯ THẾ: Nhìn thẳng (Yaw: {yaw:.1f}°, Pitch: {pitch:.1f}°)")

    # C. YOLOv8 object alerts
    if objects:
        person_count = objects.get("person_count", 0)
        max_persons = objects.get("max_persons", 1)
        if person_count > max_persons:
            alerts.append(f"Phát hiện {person_count} người trong khung hình!")

        for det in objects.get("detections", []):
            level = det.get("level", "OK")
            label = det.get("label", det["class"])
            conf = det["confidence"]

            if level == "CRITICAL":
                alerts.append(f"GIAN LẬN: {label} ({conf:.2f})")
            elif level == "WARNING":
                alerts.append(f"CẢNH BÁO: {label} ({conf:.2f})")
            elif level == "OK":
                alerts.append(f"HỢP LỆ: {label} ({conf:.2f})")

    return alerts


# ------------------------------------------------------------------
# 8. SERVE STATIC FRONTEND
# ------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
