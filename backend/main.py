"""
main.py — FastAPI application entry point.
Integrates SQLite database with authentication, role-based access control,
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
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.ai_engine import AIEngine
from backend.config import ANCHOR_DIR, LOG_DIR
from backend.database import get_db, engine, Base
from backend.models import User, ExamRoom, RoomStudent, ExamSession, ViolationLog
from backend.auth import (
    get_password_hash,
    verify_password,
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
    RoomResponse,
    RoomStudentEnroll,
    ExamSessionStart,
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
    logger.info("🚀 KHỞI CHẠY Hệ thống Anti-Cheat tích hợp Database SQLite...")
    logger.info("=" * 60)

    # Automatically create SQLite tables if not exist
    Base.metadata.create_all(bind=engine.connector if hasattr(engine, 'connector') else engine.engine if hasattr(engine, 'engine') else engine.connect() if hasattr(engine, 'connect') else Base.metadata.bind if Base.metadata.bind else engine)
    
    # Load all 3 AI models into RAM
    engine.load_models()

    # Load legacy anchors from data/anchor/ for fallback
    engine.load_anchors(ANCHOR_DIR)

    logger.info(f"✅ Đã nạp xong models và {len(engine.anchor_db)} anchors tham chiếu.")
    logger.info("✨ Hệ thống SẴN SÀNG. Chờ kết nối...")
    logger.info("=" * 60)

    yield  # Application runs here

    logger.info("🛑 Tắt Hệ thống Anti-Cheat.")


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
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Registers a new user in the system."""
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Tên đăng nhập đã tồn tại trong hệ thống."
        )

    if user_data.mssv:
        existing_mssv = db.query(User).filter(User.mssv == user_data.mssv).first()
        if existing_mssv:
            raise HTTPException(
                status_code=400,
                detail="Mã số sinh viên (MSSV) đã được đăng ký."
            )

    hashed_pw = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        hashed_password=hashed_pw,
        role=user_data.role,
        full_name=user_data.full_name,
        mssv=user_data.mssv
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Logs in a user and returns a JWT access token."""
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác."
        )

    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Retrieves current user details using access token."""
    return current_user


# ------------------------------------------------------------------
# 2. EXAM ROOM DIVISION API
# ------------------------------------------------------------------

@app.post("/api/rooms/create", response_model=RoomResponse)
async def create_room(
    room_data: RoomCreate,
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """Creates a new exam room. Restricted to teachers and admins."""
    existing_room = db.query(ExamRoom).filter(ExamRoom.room_code == room_data.room_code).first()
    if existing_room:
        raise HTTPException(
            status_code=400,
            detail="Mã phòng thi đã tồn tại."
        )

    new_room = ExamRoom(
        room_code=room_data.room_code,
        title=room_data.title,
        description=room_data.description,
        teacher_id=current_user.id
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room


@app.get("/api/rooms/teacher-rooms", response_model=List[RoomResponse])
async def get_teacher_rooms(
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """Retrieves all exam rooms created by the current teacher."""
    rooms = db.query(ExamRoom).filter(ExamRoom.teacher_id == current_user.id).all()
    return rooms


@app.get("/api/rooms/student-rooms", response_model=List[RoomResponse])
async def get_student_rooms(
    current_user: User = Depends(require_role(["student"])),
    db: Session = Depends(get_db)
):
    """Retrieves all exam rooms the student is enrolled in."""
    enrollments = db.query(RoomStudent).filter(RoomStudent.student_id == current_user.id).all()
    rooms = [enroll.room for enroll in enrollments]
    return rooms


@app.post("/api/rooms/enroll")
async def enroll_student(
    enroll_data: RoomStudentEnroll,
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """Enrolls a student into an exam room using their MSSV."""
    room = db.query(ExamRoom).filter(ExamRoom.room_code == enroll_data.room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")

    student = db.query(User).filter(User.mssv == enroll_data.mssv, User.role == "student").first()
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên có MSSV này.")

    # Check if already enrolled
    existing = db.query(RoomStudent).filter(
        RoomStudent.room_id == room.id,
        RoomStudent.student_id == student.id
    ).first()
    if existing:
        return {"status": "ok", "message": "Sinh viên đã được ghi danh trong phòng thi này."}

    # Dynamic path for anchor back up
    photo_path = None
    anchor_filename = f"{student.mssv}_HuynhMinhSang.jpg" if student.mssv == "2380601889" else None
    if anchor_filename and os.path.exists(os.path.join(ANCHOR_DIR, anchor_filename)):
        photo_path = os.path.join(ANCHOR_DIR, anchor_filename)

    new_enroll = RoomStudent(
        room_id=room.id,
        student_id=student.id,
        face_image_path=photo_path
    )
    db.add(new_enroll)
    db.commit()
    return {"status": "ok", "message": f"Ghi danh thành công sinh viên {student.full_name} vào phòng {room.title}."}


@app.get("/api/rooms/{room_code}/students")
async def get_room_students(
    room_code: str,
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """Retrieves all students enrolled in a specific room."""
    room = db.query(ExamRoom).filter(ExamRoom.room_code == room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")
        
    enrollments = db.query(RoomStudent).filter(RoomStudent.room_id == room.id).all()
    result = []
    for e in enrollments:
        s = e.student
        result.append({
            "id": s.id,
            "username": s.username,
            "full_name": s.full_name,
            "mssv": s.mssv,
            "has_face_registered": e.face_embedding is not None or e.face_image_path is not None
        })
    return result


# ------------------------------------------------------------------
# 3. EXAM SESSION FLOW & REAL-TIME LOGGING API
# ------------------------------------------------------------------

@app.post("/api/exam/start")
async def start_exam(
    payload: ExamSessionStart,
    current_user: User = Depends(require_role(["student"])),
    db: Session = Depends(get_db)
):
    """Starts a student's active exam session and dynamically loads reference faces for this room."""
    room = db.query(ExamRoom).filter(ExamRoom.room_code == payload.room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")

    # Check if student is enrolled in this room
    enrollment = db.query(RoomStudent).filter(
        RoomStudent.room_id == room.id,
        RoomStudent.student_id == current_user.id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=403, detail="Bạn không được ghi danh trong phòng thi này.")

    # Terminate any previously unsubmitted session
    active_sessions = db.query(ExamSession).filter(
        ExamSession.student_id == current_user.id,
        ExamSession.ended_at == None
    ).all()
    for s in active_sessions:
        s.ended_at = datetime.utcnow()
        db.add(s)

    # Clear current RAM anchors and dynamically load only this room's student face embeddings!
    engine.anchor_db = {}
    engine.load_db_anchors(db, room.id)

    # Create new exam session
    new_session = ExamSession(
        room_id=room.id,
        student_id=current_user.id,
        status="NORMAL"
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "status": "ok",
        "message": f"Bắt đầu phiên làm bài tại phòng {room.title}.",
        "session_id": new_session.id,
        "room_title": room.title
    }


@app.post("/api/exam/submit")
async def submit_exam(
    current_user: User = Depends(require_role(["student"])),
    db: Session = Depends(get_db)
):
    """Ends the student's currently active exam session."""
    active_session = db.query(ExamSession).filter(
        ExamSession.student_id == current_user.id,
        ExamSession.ended_at == None
    ).order_by(ExamSession.started_at.desc()).first()

    if not active_session:
        raise HTTPException(status_code=400, detail="Không tìm thấy phiên làm bài đang chạy.")

    active_session.ended_at = datetime.utcnow()
    db.add(active_session)
    db.commit()

    # Reload fallback anchors
    engine.anchor_db = {}
    engine.load_anchors(ANCHOR_DIR)

    return {"status": "ok", "message": "Đã nộp bài và dừng phiên giám sát thành công."}


@app.get("/api/rooms/{room_code}/status")
async def get_room_live_status(
    room_code: str,
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """
    Retrieves real-time status of all student sessions in a room (Live Monitor Dashboard).
    """
    room = db.query(ExamRoom).filter(ExamRoom.room_code == room_code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng thi.")

    enrollments = db.query(RoomStudent).filter(RoomStudent.room_id == room.id).all()
    results = []
    
    for enroll in enrollments:
        student = enroll.student
        
        # Get active session
        active_sess = db.query(ExamSession).filter(
            ExamSession.room_id == room.id,
            ExamSession.student_id == student.id,
            ExamSession.ended_at == None
        ).order_by(ExamSession.started_at.desc()).first()

        if active_sess:
            status_str = active_sess.status
            violation_count = active_sess.violation_count
            started_at = active_sess.started_at.strftime("%H:%M:%S")
            is_active = True
        else:
            # Query last ended session
            last_sess = db.query(ExamSession).filter(
                ExamSession.room_id == room.id,
                ExamSession.student_id == student.id
            ).order_by(ExamSession.started_at.desc()).first()
            
            status_str = last_sess.status if last_sess else "NORMAL"
            violation_count = last_sess.violation_count if last_sess else 0
            started_at = last_sess.started_at.strftime("%Y-%m-%d %H:%M") if last_sess else "Chưa thi"
            is_active = False

        results.append({
            "mssv": student.mssv,
            "full_name": student.full_name,
            "is_active": is_active,
            "started_at": started_at,
            "violation_count": violation_count,
            "status": status_str
        })

    return {"room_title": room.title, "room_code": room_code, "students": results}


@app.get("/api/logs/violations")
async def get_violation_logs(
    room_code: Optional[str] = Query(None),
    mssv: Optional[str] = Query(None),
    limit: int = Query(50),
    current_user: User = Depends(require_role(["admin", "teacher"])),
    db: Session = Depends(get_db)
):
    """
    Queries violation logs with filters. Supports premium visual screenshots.
    """
    query = db.query(ViolationLog)

    if room_code:
        room = db.query(ExamRoom).filter(ExamRoom.room_code == room_code).first()
        if room:
            query = query.filter(ViolationLog.room_id == room.id)
            
    if mssv:
        student = db.query(User).filter(User.mssv == mssv).first()
        if student:
            query = query.filter(ViolationLog.student_id == student.id)

    logs = query.order_by(ViolationLog.timestamp.desc()).limit(limit).all()
    results = []
    
    for log in logs:
        # Check screenshot exists
        img_url = None
        if log.frame_image_path and os.path.exists(log.frame_image_path):
            # Expose base64 or absolute link. Since we can serve images, let's return absolute path or serve it
            img_url = f"/api/violations/image/{log.id}"

        results.append({
            "id": log.id,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "room_code": log.room.room_code,
            "room_title": log.room.title,
            "mssv": log.student.mssv,
            "student_name": log.student.full_name,
            "violation_type": log.violation_type,
            "severity": log.severity,
            "similarity_score": log.similarity_score,
            "details": log.details,
            "image_url": img_url
        })
        
    return results


@app.get("/api/violations/image/{log_id}")
async def get_violation_image(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Serves the cheating visual screenshot for audit purposes."""
    log = db.query(ViolationLog).filter(ViolationLog.id == log_id).first()
    if not log or not log.frame_image_path or not os.path.exists(log.frame_image_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh bằng chứng.")

    from fastapi.responses import FileResponse
    return FileResponse(log.frame_image_path)


# ------------------------------------------------------------------
# 4. FRAME PROCESSING API (INTEGRATING SQLite DATABASE LOGGING)
# ------------------------------------------------------------------

@app.post("/api/process_frame", response_model=FrameResponse)
async def process_frame(request: FrameRequest, db: Session = Depends(get_db)):
    """
    Main real-time anti-cheat AI processing engine.
    Receives JPEG base64 and student ID (MSSV), performs AI analytics,
    saves violations in SQLite DB, escalates warning count, and captures audit screenshots.
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
            alerts=[f"❌ LỖI GIẢI MÃ: {str(e)}"],
            timestamp=timestamp_str,
        )

    # 2. Query Student & Active Exam Session
    student = db.query(User).filter(User.mssv == request.mssv, User.role == "student").first()
    active_session = None
    if student:
        active_session = db.query(ExamSession).filter(
            ExamSession.student_id == student.id,
            ExamSession.ended_at == None
        ).order_by(ExamSession.started_at.desc()).first()

    # 3. Run AI Analytics Pipeline
    identity_result = engine.verify_identity(frame, request.mssv)
    
    # Tối ưu hóa: Nếu MSSV chưa đăng ký, bỏ qua bước nhận diện đồ vật (để tiết kiệm CPU)
    if identity_result["status"] == "Error":
        head_pose_result = None
        objects_result = None
    else:
        head_pose_result = engine.analyze_head_pose(frame)
        objects_result = engine.detect_objects(frame)

    # 4. Compile Human-Readable Alerts
    alerts = _build_alerts(identity_result, head_pose_result, objects_result)

    # 5. Database Logging & Warnings Escalation (If student has an active session)
    if active_session and student:
        # Determine if violations occurred in this frame
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

        # C. Banned Objects & Helper Detection (YOLOv8)
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
            
            frame_filename = f"sess_{active_session.id}_{int(datetime.now().timestamp())}.jpg"
            frame_path = os.path.join(violation_dir, frame_filename)
            cv2.imwrite(frame_path, frame)

            # Record each violation log
            for v in violations_to_log:
                new_log = ViolationLog(
                    session_id=active_session.id,
                    room_id=active_session.room_id,
                    student_id=student.id,
                    violation_type=v["type"],
                    severity=v["severity"],
                    similarity_score=v["score"],
                    details=v["details"],
                    frame_image_path=frame_path
                )
                db.add(new_log)

            # Escalate Warning Count
            active_session.violation_count += len(violations_to_log)
            if active_session.violation_count >= 5:
                active_session.status = "FLAGGED"
            elif active_session.violation_count >= 3:
                active_session.status = "SUSPICIOUS"
                
            db.add(active_session)
            db.commit()

            # Append warning escalation logs in real-time alerts
            alerts.append(f"🚨 HỆ THỐNG: Cảnh báo vi phạm tích lũy! Lần: {active_session.violation_count} (Trạng thái: {active_session.status})")

    # 6. Legacy CSV Logger fallback
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
    )


# ------------------------------------------------------------------
# 5. DYNAMIC ENROLLMENT & FALLBACK ROUTING
# ------------------------------------------------------------------

@app.post("/api/add_student")
async def add_student(
    mssv: str = Form(...),
    name: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Registers a student's face dynamically.
    Creates / updates the User account, extracts ArcFace face embedding,
    saves the reference photo, and caches it in the SQLite database.
    """
    image_bytes = await photo.read()
    if not image_bytes:
        return JSONResponse(status_code=400, content={"status": "error", "message": "❌ File ảnh trống."})

    # Call AI engine dynamic enrollment (updates in-memory anchors)
    result = engine.add_anchor(mssv, name, image_bytes)
    if result["status"] == "error":
        return JSONResponse(status_code=400, content=result)

    # Additionally, check and create User account in Database
    student = db.query(User).filter(User.mssv == mssv).first()
    if not student:
        username = f"sv_{mssv}"
        hashed_pw = get_password_hash("student123")
        student = User(
            username=username,
            hashed_password=hashed_pw,
            role="student",
            full_name=name,
            mssv=mssv
        )
        db.add(student)
        db.commit()
        db.refresh(student)

    # Save to RoomStudent database (Enroll in first exam room or all active exam rooms)
    rooms = db.query(ExamRoom).all()
    for room in rooms:
        enroll = db.query(RoomStudent).filter(
            RoomStudent.room_id == room.id,
            RoomStudent.student_id == student.id
        ).first()
        
        saved_photo_name = f"{mssv}_{name.replace(' ', '_')}.jpg"
        saved_photo_path = os.path.join(ANCHOR_DIR, saved_photo_name)
        
        # Serialize embedding float list
        embedding_val = engine.anchor_db[mssv]["embedding"]

        if not enroll:
            enroll = RoomStudent(
                room_id=room.id,
                student_id=student.id,
                face_image_path=saved_photo_path
            )
        enroll.set_embedding(embedding_val)
        db.add(enroll)
        
    db.commit()
    return result


# --- Legacy csv stats endpoints (for compatibility) ---

@app.get("/api/logs")
async def get_logs_legacy(session_id: str = Query(None), limit: int = Query(100)):
    try:
        data = csv_logger.get_session_data(session_id, limit)
        return {"status": "ok", "session_id": session_id or datetime.now().strftime("%Y%m%d"), "total_rows": len(data), "data": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"❌ Lỗi: {str(e)}"})


@app.get("/api/logs/stats")
async def get_logs_stats_legacy(session_id: str = Query(None)):
    try:
        stats = csv_logger.get_session_stats(session_id)
        return {"status": "ok", "session_id": session_id or datetime.now().strftime("%Y%m%d"), "stats": stats}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"❌ Lỗi: {str(e)}"})


@app.get("/api/logs/sessions")
async def list_sessions_legacy():
    try:
        sessions = csv_logger.list_sessions()
        return {"status": "ok", "sessions": sessions, "total_sessions": len(sessions)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"❌ Lỗi: {str(e)}"})


# ------------------------------------------------------------------
# 6. SYSTEM ALERTS COMPILATION
# ------------------------------------------------------------------

def _build_alerts(identity: dict, head_pose: dict | None, objects: dict | None) -> list[str]:
    """Compiles human-readable alert strings from model predictions."""
    alerts = []

    # A. Face matching identity alert
    if identity["status"] == "Match":
        alerts.append(f"✅ ĐÚNG NGƯỜI: {identity['name']} (sim: {identity['similarity']})")
    elif identity["status"] == "Unknown":
        alerts.append(f"⚠️ SAI NGƯỜI: Phát hiện gian lận (sim: {identity['similarity']})")
    elif identity["status"] == "Error":
        alerts.append(f"❌ LỖI: MSSV chưa được đăng ký khuôn mặt")
    else:
        alerts.append(f"⚠️ KHÔNG CÓ KHUÔN MẶT")

    # B. MediaPipe Head pose alerts
    if head_pose:
        pass

    # C. YOLOv8 object alerts
    if objects:
        person_count = objects.get("person_count", 0)
        max_persons = objects.get("max_persons", 1)
        if person_count > max_persons:
            alerts.append(f"🚨 CRITICAL: Phát hiện {person_count} người trong khung hình!")

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
# 7. SERVE STATIC FRONTEND
# ------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
