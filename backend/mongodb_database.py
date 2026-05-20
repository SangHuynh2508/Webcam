"""
mongodb_database.py — MongoDB database helper and operations adapter.
Provides high-performance operations using PyMongo for registering, logging in,
authorizing roles, dividing exam rooms, updating student face embeddings,
and logging cheating violations with cumulative warning escalations.
"""
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pymongo import MongoClient
from backend.auth import get_password_hash, verify_password

# --- Configuration ---
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "anti_cheat_db")

class MongoDBHelper:
    """
    Adapter class for MongoDB containing all required database operations
    for the Webcam Exam Cheating Detection system.
    """
    def __init__(self, uri: str = MONGODB_URI, db_name: str = DB_NAME):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        
        # Reference collections
        self.users = self.db["users"]
        self.rooms = self.db["exam_rooms"]
        self.sessions = self.db["exam_sessions"]
        self.logs = self.db["violation_logs"]
        self.settings = self.db["system_settings"]

    # ------------------------------------------------------------------
    # 1. AUTHENTICATION & USER MANAGEMENT
    # ------------------------------------------------------------------
    def register_user(
        self, username: str, password_plain: str, role: str, full_name: str, mssv: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registers a new user in the MongoDB 'users' collection.
        Hashes password using bcrypt.
        """
        # Validate unique username
        if self.users.find_one({"username": username}):
            raise ValueError("Tên đăng nhập đã tồn tại trong hệ thống.")

        # Validate unique MSSV if student
        if role == "student" and mssv:
            if self.users.find_one({"mssv": mssv}):
                raise ValueError("Mã số sinh viên (MSSV) đã được đăng ký.")

        hashed_password = get_password_hash(password_plain)
        
        user_doc = {
            "username": username,
            "hashed_password": hashed_password,
            "role": role,  # "admin", "teacher", "student"
            "full_name": full_name,
            "mssv": mssv if role == "student" else None,
            "created_at": datetime.utcnow()
        }
        
        result = self.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        return user_doc

    def authenticate_user(self, username: str, password_plain: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates a user and returns their user document if password matches.
        """
        user_doc = self.users.find_one({"username": username})
        if not user_doc:
            return None
            
        if verify_password(password_plain, user_doc["hashed_password"]):
            return user_doc
        return None

    def get_user_by_id(self, user_id: Any) -> Optional[Dict[str, Any]]:
        """Retrieves a user by their MongoDB ObjectId."""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return self.users.find_one({"_id": user_id})

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user by their username."""
        return self.users.find_one({"username": username})

    # ------------------------------------------------------------------
    # 2. EXAM ROOM DIVISION & ENROLLMENT
    # ------------------------------------------------------------------
    def create_room(self, room_code: str, title: str, description: str, teacher_id: Any) -> Dict[str, Any]:
        """
        Creates a new exam room with an empty student list.
        """
        if self.rooms.find_one({"room_code": room_code}):
            raise ValueError("Mã phòng thi đã tồn tại.")

        if isinstance(teacher_id, str):
            teacher_id = ObjectId(teacher_id)

        room_doc = {
            "room_code": room_code,
            "title": title,
            "description": description,
            "teacher_id": teacher_id,
            "students": [],  # Embedded array containing enrolled students and their face data
            "created_at": datetime.utcnow()
        }

        result = self.rooms.insert_one(room_doc)
        room_doc["_id"] = result.inserted_id
        return room_doc

    def get_rooms_by_teacher(self, teacher_id: Any) -> List[Dict[str, Any]]:
        """Retrieves all rooms created by a teacher."""
        if isinstance(teacher_id, str):
            teacher_id = ObjectId(teacher_id)
        return list(self.rooms.find({"teacher_id": teacher_id}))

    def get_rooms_by_student(self, student_id: Any) -> List[Dict[str, Any]]:
        """Retrieves all rooms that the student is enrolled in."""
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)
        return list(self.rooms.find({"students.student_id": student_id}))

    def enroll_student(self, room_code: str, mssv: str, face_image_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Enrolls a student into an exam room using their MSSV card.
        Embeds the student structure directly in the room document for fast face descriptor loading.
        """
        room = self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        student = self.users.find_one({"mssv": mssv, "role": "student"})
        if not student:
            raise ValueError("Không tìm thấy sinh viên có MSSV này.")

        # Check if already enrolled in the room
        already_enrolled = False
        for s in room.get("students", []):
            if s["student_id"] == student["_id"]:
                already_enrolled = True
                break

        if already_enrolled:
            return {"status": "ok", "message": "Sinh viên đã được ghi danh trong phòng thi này."}

        # Structure for student embedded enrollment
        student_enrollment = {
            "student_id": student["_id"],
            "face_embedding": None,  # Will be stored as 512 double float array once registered
            "face_image_path": face_image_path,
            "enrolled_at": datetime.utcnow()
        }

        self.rooms.update_one(
            {"_id": room["_id"]},
            {"$push": {"students": student_enrollment}}
        )

        return {"status": "ok", "message": f"Ghi danh thành công sinh viên {student['full_name']} vào phòng {room['title']}."}

    def get_room_students(self, room_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves all students enrolled in a room with their status details.
        """
        room = self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        results = []
        for e in room.get("students", []):
            student_doc = self.get_user_by_id(e["student_id"])
            if student_doc:
                results.append({
                    "id": str(student_doc["_id"]),
                    "username": student_doc["username"],
                    "full_name": student_doc["full_name"],
                    "mssv": student_doc["mssv"],
                    "has_face_registered": e.get("face_embedding") is not None or e.get("face_image_path") is not None
                })
        return results

    # ------------------------------------------------------------------
    # 3. STUDENT FACE EMBEDDINGS MANAGEMENT
    # ------------------------------------------------------------------
    def update_student_face_data(self, mssv: str, embedding: List[float], face_image_path: Optional[str] = None) -> bool:
        """
        Updates the student's face embedding (ArcFace float vector) and photo path 
        across all rooms they are enrolled in.
        """
        student = self.users.find_one({"mssv": mssv, "role": "student"})
        if not student:
            return False

        # Build updates dynamically
        update_fields: Dict[str, Any] = {
            "students.$.face_embedding": embedding
        }
        if face_image_path:
            update_fields["students.$.face_image_path"] = face_image_path

        # Update in all rooms where this student is listed in the students array
        self.rooms.update_many(
            {"students.student_id": student["_id"]},
            {"$set": update_fields}
        )
        return True

    # ------------------------------------------------------------------
    # 4. EXAM SESSION FLOW & MONITORING
    # ------------------------------------------------------------------
    def start_exam_session(self, room_code: str, student_id: Any) -> Dict[str, Any]:
        """
        Starts an active exam session for a student in a room.
        Terminates any previously unclosed sessions for that student automatically.
        """
        room = self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        if isinstance(student_id, str):
            student_id = ObjectId(student_id)

        # Check if student is enrolled in this room
        enrolled = False
        for s in room.get("students", []):
            if s["student_id"] == student_id:
                enrolled = True
                break
        
        if not enrolled:
            raise PermissionError("Bạn không được ghi danh trong phòng thi này.")

        # Close any unclosed sessions for the student
        self.sessions.update_many(
            {"student_id": student_id, "ended_at": None},
            {"$set": {"ended_at": datetime.utcnow()}}
        )

        session_doc = {
            "room_id": room["_id"],
            "student_id": student_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "violation_count": 0,
            "status": "NORMAL"  # "NORMAL", "SUSPICIOUS", "FLAGGED"
        }

        result = self.sessions.insert_one(session_doc)
        session_doc["_id"] = result.inserted_id
        return session_doc

    def submit_exam_session(self, student_id: Any) -> bool:
        """
        Ends the student's currently active exam session.
        """
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)

        result = self.sessions.update_one(
            {"student_id": student_id, "ended_at": None},
            {"$set": {"ended_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    def get_room_live_status(self, room_code: str) -> Dict[str, Any]:
        """
        Retrieves real-time monitoring statuses of all enrolled students in a room.
        """
        room = self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        results = []
        for enroll in room.get("students", []):
            student = self.get_user_by_id(enroll["student_id"])
            if not student:
                continue

            # Query active session
            active_sess = self.sessions.find_one(
                {"room_id": room["_id"], "student_id": student["_id"], "ended_at": None},
                sort=[("started_at", -1)]
            )

            if active_sess:
                status_str = active_sess["status"]
                violation_count = active_sess["violation_count"]
                started_at = active_sess["started_at"].strftime("%H:%M:%S")
                is_active = True
            else:
                # Query last ended session
                last_sess = self.sessions.find_one(
                    {"room_id": room["_id"], "student_id": student["_id"]},
                    sort=[("started_at", -1)]
                )
                status_str = last_sess["status"] if last_sess else "NORMAL"
                violation_count = last_sess["violation_count"] if last_sess else 0
                started_at = last_sess["started_at"].strftime("%Y-%m-%d %H:%M") if last_sess else "Chưa thi"
                is_active = False

            results.append({
                "mssv": student["mssv"],
                "full_name": student["full_name"],
                "is_active": is_active,
                "started_at": started_at,
                "violation_count": violation_count,
                "status": status_str
            })

        return {"room_title": room["title"], "room_code": room_code, "students": results}

    # ------------------------------------------------------------------
    # 5. VIOLATION LOGGING & WARNING LEVEL ESCALATION
    # ------------------------------------------------------------------
    def log_violation(
        self,
        session_id: Any,
        room_id: Any,
        student_id: Any,
        violation_type: str,
        severity: str,
        similarity_score: Optional[float] = None,
        details: str = "",
        frame_image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Logs a single cheating violation, increments active session violation count,
        and escalates student status flags dynamically (NORMAL -> SUSPICIOUS -> FLAGGED).
        """
        if isinstance(session_id, str):
            session_id = ObjectId(session_id)
        if isinstance(room_id, str):
            room_id = ObjectId(room_id)
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)

        log_doc = {
            "session_id": session_id,
            "room_id": room_id,
            "student_id": student_id,
            "timestamp": datetime.utcnow(),
            "violation_type": violation_type,
            "severity": severity,  # "CRITICAL", "WARNING"
            "similarity_score": similarity_score,
            "details": details,
            "frame_image_path": frame_image_path
        }

        # Insert audit log document
        result = self.logs.insert_one(log_doc)
        log_doc["_id"] = result.inserted_id

        # Fetch custom thresholds if available, otherwise fall back to standard settings
        sys_settings = self.settings.find_one({"_id": "global_ai_config"})
        limit_suspicious = sys_settings.get("max_violations_suspicious", 3) if sys_settings else 3
        limit_flagged = sys_settings.get("max_violations_flagged", 5) if sys_settings else 5

        # Escalate Warning Counts inside session
        session = self.sessions.find_one({"_id": session_id})
        if session:
            new_count = session.get("violation_count", 0) + 1
            
            # Determine warnings status escalation
            new_status = "NORMAL"
            if new_count >= limit_flagged:
                new_status = "FLAGGED"
            elif new_count >= limit_suspicious:
                new_status = "SUSPICIOUS"

            self.sessions.update_one(
                {"_id": session_id},
                {"$set": {"violation_count": new_count, "status": new_status}}
            )

        return log_doc

    def get_violation_logs(self, room_code: Optional[str] = None, mssv: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves violation log histories filtered by room and/or student, sorted by descending timestamp.
        """
        filter_query: Dict[str, Any] = {}

        if room_code:
            room = self.rooms.find_one({"room_code": room_code})
            if room:
                filter_query["room_id"] = room["_id"]

        if mssv:
            student = self.users.find_one({"mssv": mssv, "role": "student"})
            if student:
                filter_query["student_id"] = student["_id"]

        cursor = self.logs.find(filter_query).sort("timestamp", -1).limit(limit)
        results = []
        
        for log in cursor:
            room_doc = self.rooms.find_one({"_id": log["room_id"]})
            student_doc = self.get_user_by_id(log["student_id"])
            
            # Form image endpoints URL path matching original SQLite design
            img_url = f"/api/violations/image/{str(log['_id'])}" if log.get("frame_image_path") else None

            results.append({
                "id": str(log["_id"]),
                "timestamp": log["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "room_code": room_doc["room_code"] if room_doc else "Unknown",
                "room_title": room_doc["title"] if room_doc else "Unknown",
                "mssv": student_doc["mssv"] if student_doc else "Unknown",
                "student_name": student_doc["full_name"] if student_doc else "Unknown",
                "violation_type": log["violation_type"],
                "severity": log["severity"],
                "similarity_score": log.get("similarity_score"),
                "details": log["details"],
                "image_url": img_url
            })

        return results
