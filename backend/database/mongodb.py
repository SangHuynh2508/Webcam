"""
mongodb.py — Async MongoDB repository using Motor.
Provides high-performance CRUD and utility operations.
"""
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


# --- Configuration ---
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "anti_cheat_db")

class MongoDBRepository:
    def __init__(self, uri: str = MONGODB_URI, db_name: str = DB_NAME):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.rooms = self.db["exam_rooms"]
        self.sessions = self.db["exam_sessions"]
        self.logs = self.db["violation_logs"]
        self.settings = self.db["system_settings"]

    def _serialize_doc(self, doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        doc = doc.copy()
        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            # Keep _id but provide id as string for API compatibility
        
        # Serialize fields like ObjectIds and datetimes if needed
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                doc[k] = str(v)
            elif isinstance(v, datetime):
                # Kept as datetime objects, but sub-serialization can convert to strings if needed
                pass
            elif isinstance(v, list):
                # If there are sub-documents (like students in exam_rooms)
                doc[k] = [self._serialize_doc(item) if isinstance(item, dict) else item for item in v]
        return doc

    # 1. AUTHENTICATION & USER MANAGEMENT
    async def register_user(
        self, username: str, password_plain: str, role: str, full_name: str, mssv: Optional[str] = None
    ) -> Dict[str, Any]:
        if await self.users.find_one({"username": username}):
            raise ValueError("Tên đăng nhập đã tồn tại trong hệ thống.")

        if role == "student" and mssv:
            if await self.users.find_one({"mssv": mssv}):
                raise ValueError("Mã số sinh viên (MSSV) đã được đăng ký.")

        from backend.auth import get_password_hash
        hashed_password = get_password_hash(password_plain)
        user_doc = {
            "username": username,
            "hashed_password": hashed_password,
            "role": role,  # "admin", "teacher", "student"
            "full_name": full_name,
            "created_at": datetime.utcnow()
        }
        if role == "student" and mssv:
            user_doc["mssv"] = mssv
        result = await self.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        return self._serialize_doc(user_doc)

    async def authenticate_user(self, username: str, password_plain: str) -> Optional[Dict[str, Any]]:
        user_doc = await self.users.find_one({"username": username})
        if not user_doc:
            return None
        from backend.auth import verify_password
        if verify_password(password_plain, user_doc["hashed_password"]):
            return self._serialize_doc(user_doc)
        return None

    async def get_user_by_id(self, user_id: Any) -> Optional[Dict[str, Any]]:
        if isinstance(user_id, str):
            try:
                user_id = ObjectId(user_id)
            except Exception:
                return None
        doc = await self.users.find_one({"_id": user_id})
        return self._serialize_doc(doc)

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        doc = await self.users.find_one({"username": username})
        return self._serialize_doc(doc)

    async def update_user(self, username: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Remove protected fields
        updates = {k: v for k, v in updates.items() if k not in ["_id", "id", "username", "created_at"]}
        if "password" in updates:
            from backend.auth import get_password_hash
            updates["hashed_password"] = get_password_hash(updates.pop("password"))
        
        result = await self.users.find_one_and_update(
            {"username": username},
            {"$set": updates},
            return_document=True
        )
        return self._serialize_doc(result)

    async def delete_user(self, username: str) -> bool:
        user = await self.users.find_one({"username": username})
        if not user:
            return False
        
        # Delete user
        await self.users.delete_one({"_id": user["_id"]})
        
        # Cascade: remove from rooms students array
        await self.rooms.update_many(
            {"students.student_id": user["_id"]},
            {"$pull": {"students": {"student_id": user["_id"]}}}
        )
        
        # Cascade: delete sessions and violation logs
        await self.sessions.delete_many({"student_id": user["_id"]})
        await self.logs.delete_many({"student_id": user["_id"]})
        return True

    # 2. EXAM ROOMS
    async def create_room(self, room_code: str, title: str, description: str, teacher_id: Any) -> Dict[str, Any]:
        if await self.rooms.find_one({"room_code": room_code}):
            raise ValueError("Mã phòng thi đã tồn tại.")

        if isinstance(teacher_id, str):
            teacher_id = ObjectId(teacher_id)

        room_doc = {
            "room_code": room_code,
            "title": title,
            "description": description,
            "teacher_id": teacher_id,
            "students": [],
            "created_at": datetime.utcnow()
        }
        result = await self.rooms.insert_one(room_doc)
        room_doc["_id"] = result.inserted_id
        return self._serialize_doc(room_doc)

    async def get_rooms_by_teacher(self, teacher_id: Any) -> List[Dict[str, Any]]:
        if isinstance(teacher_id, str):
            teacher_id = ObjectId(teacher_id)
        cursor = self.rooms.find({"teacher_id": teacher_id})
        return [self._serialize_doc(doc) for doc in await cursor.to_list(length=1000)]

    async def get_rooms_by_student(self, student_id: Any) -> List[Dict[str, Any]]:
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)
        cursor = self.rooms.find({"students.student_id": student_id})
        return [self._serialize_doc(doc) for doc in await cursor.to_list(length=1000)]

    async def get_room_by_code(self, room_code: str) -> Optional[Dict[str, Any]]:
        doc = await self.rooms.find_one({"room_code": room_code})
        return self._serialize_doc(doc)

    async def update_room(self, room_code: str, title: str, description: str) -> Optional[Dict[str, Any]]:
        result = await self.rooms.find_one_and_update(
            {"room_code": room_code},
            {"$set": {"title": title, "description": description}},
            return_document=True
        )
        return self._serialize_doc(result)

    async def delete_room(self, room_code: str) -> bool:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            return False
        
        await self.rooms.delete_one({"_id": room["_id"]})
        # Cascade: delete sessions and logs associated with the room
        await self.sessions.delete_many({"room_id": room["_id"]})
        await self.logs.delete_many({"room_id": room["_id"]})
        return True

    # 3. ROOM ENROLLMENTS & FACE EMBEDDINGS
    async def enroll_student(self, room_code: str, mssv: str, face_image_path: Optional[str] = None) -> Dict[str, Any]:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        student = await self.users.find_one({"mssv": mssv, "role": "student"})
        if not student:
            raise ValueError("Không tìm thấy sinh viên có MSSV này.")

        # Check if already enrolled in the room
        already_enrolled = any(s["student_id"] == student["_id"] for s in room.get("students", []))
        if already_enrolled:
            return {"status": "ok", "message": "Sinh viên đã được ghi danh trong phòng thi này."}

        student_enrollment = {
            "student_id": student["_id"],
            "face_embedding": None,
            "face_image_path": face_image_path,
            "enrolled_at": datetime.utcnow()
        }

        await self.rooms.update_one(
            {"_id": room["_id"]},
            {"$push": {"students": student_enrollment}}
        )
        return {"status": "ok", "message": f"Ghi danh thành công sinh viên {student['full_name']} vào phòng {room['title']}."}

    async def unenroll_student(self, room_code: str, mssv: str) -> bool:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        student = await self.users.find_one({"mssv": mssv, "role": "student"})
        if not student:
            raise ValueError("Không tìm thấy sinh viên có MSSV này.")

        result = await self.rooms.update_one(
            {"_id": room["_id"]},
            {"$pull": {"students": {"student_id": student["_id"]}}}
        )
        return result.modified_count > 0

    async def get_room_students(self, room_code: str) -> List[Dict[str, Any]]:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        results = []
        for e in room.get("students", []):
            student_doc = await self.get_user_by_id(e["student_id"])
            if student_doc:
                results.append({
                    "id": student_doc["id"],
                    "username": student_doc["username"],
                    "full_name": student_doc["full_name"],
                    "mssv": student_doc["mssv"],
                    "has_face_registered": e.get("face_embedding") is not None or e.get("face_image_path") is not None
                })
        return results

    async def get_room_anchors(self, room_code: str) -> List[Dict[str, Any]]:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            return []
        
        results = []
        for e in room.get("students", []):
            student_doc = await self.get_user_by_id(e["student_id"])
            if student_doc and student_doc.get("mssv"):
                results.append({
                    "mssv": student_doc["mssv"],
                    "name": student_doc["full_name"],
                    "embedding": e.get("face_embedding"),
                    "face_image_path": e.get("face_image_path")
                })
        return results

    async def update_student_face_data(self, mssv: str, embedding: List[float], face_image_path: Optional[str] = None) -> bool:
        student = await self.users.find_one({"mssv": mssv, "role": "student"})
        if not student:
            return False

        update_fields: Dict[str, Any] = {
            "students.$.face_embedding": embedding
        }
        if face_image_path:
            update_fields["students.$.face_image_path"] = face_image_path

        await self.rooms.update_many(
            {"students.student_id": student["_id"]},
            {"$set": update_fields}
        )
        return True

    # 4. EXAM SESSION FLOW & MONITORING
    async def start_exam_session(self, room_code: str, student_id: Any) -> Dict[str, Any]:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        if isinstance(student_id, str):
            student_id = ObjectId(student_id)

        # Check if student is enrolled
        enrolled = any(s["student_id"] == student_id for s in room.get("students", []))
        if not enrolled:
            raise PermissionError("Bạn không được ghi danh trong phòng thi này.")

        # Close unclosed sessions
        await self.sessions.update_many(
            {"student_id": student_id, "ended_at": None},
            {"$set": {"ended_at": datetime.utcnow()}}
        )

        session_doc = {
            "room_id": room["_id"],
            "student_id": student_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "violation_count": 0,
            "status": "NORMAL"
        }
        result = await self.sessions.insert_one(session_doc)
        session_doc["_id"] = result.inserted_id
        return self._serialize_doc(session_doc)

    async def submit_exam_session(self, student_id: Any) -> bool:
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)

        result = await self.sessions.update_one(
            {"student_id": student_id, "ended_at": None},
            {"$set": {"ended_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def get_room_live_status(self, room_code: str) -> Dict[str, Any]:
        room = await self.rooms.find_one({"room_code": room_code})
        if not room:
            raise ValueError("Không tìm thấy phòng thi.")

        results = []
        for enroll in room.get("students", []):
            student = await self.get_user_by_id(enroll["student_id"])
            if not student:
                continue

            active_sess = await self.sessions.find_one(
                {"room_id": room["_id"], "student_id": ObjectId(student["id"]), "ended_at": None},
                sort=[("started_at", -1)]
            )

            if active_sess:
                status_str = active_sess["status"]
                violation_count = active_sess["violation_count"]
                started_at = active_sess["started_at"].strftime("%H:%M:%S")
                is_active = True
            else:
                last_sess = await self.sessions.find_one(
                    {"room_id": room["_id"], "student_id": ObjectId(student["id"])},
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

    # 5. VIOLATION LOGGING & WARNINGS
    async def log_violation(
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
            "severity": severity,
            "similarity_score": similarity_score,
            "details": details,
            "frame_image_path": frame_image_path
        }
        result = await self.logs.insert_one(log_doc)
        log_doc["_id"] = result.inserted_id

        # Warning Escalation
        sys_settings = await self.settings.find_one({"_id": "global_ai_config"})
        limit_suspicious = sys_settings.get("max_violations_suspicious", 3) if sys_settings else 3
        limit_flagged = sys_settings.get("max_violations_flagged", 5) if sys_settings else 5

        session = await self.sessions.find_one({"_id": session_id})
        if session:
            new_count = session.get("violation_count", 0) + 1
            new_status = "NORMAL"
            if new_count >= limit_flagged:
                new_status = "FLAGGED"
            elif new_count >= limit_suspicious:
                new_status = "SUSPICIOUS"

            await self.sessions.update_one(
                {"_id": session_id},
                {"$set": {"violation_count": new_count, "status": new_status}}
            )

        return self._serialize_doc(log_doc)

    async def get_violation_logs(self, room_code: Optional[str] = None, mssv: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        filter_query: Dict[str, Any] = {}

        if room_code:
            room = await self.rooms.find_one({"room_code": room_code})
            if room:
                filter_query["room_id"] = room["_id"]

        if mssv:
            student = await self.users.find_one({"mssv": mssv, "role": "student"})
            if student:
                filter_query["student_id"] = student["_id"]

        cursor = self.logs.find(filter_query).sort("timestamp", -1).limit(limit)
        results = []
        for log in await cursor.to_list(length=limit):
            room_doc = await self.rooms.find_one({"_id": log["room_id"]})
            student_doc = await self.get_user_by_id(log["student_id"])
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

    async def get_violation_log_by_id(self, log_id: str) -> Optional[Dict[str, Any]]:
        try:
            oid = ObjectId(log_id)
        except Exception:
            return None
        doc = await self.logs.find_one({"_id": oid})
        return self._serialize_doc(doc)

    # 6. SYSTEM SETTINGS
    async def get_system_settings(self) -> Dict[str, Any]:
        doc = await self.settings.find_one({"_id": "global_ai_config"})
        if not doc:
            # Fallback defaults
            return {
                "id": "global_ai_config",
                "face_similarity_threshold": 0.55,
                "head_yaw_threshold": 30.0,
                "head_pitch_threshold": 25.0,
                "yolo_confidence_threshold": 0.65,
                "max_violations_suspicious": 3,
                "max_violations_flagged": 5
            }
        return self._serialize_doc(doc)

    async def update_system_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed_fields = [
            "face_similarity_threshold",
            "head_yaw_threshold",
            "head_pitch_threshold",
            "yolo_confidence_threshold",
            "max_violations_suspicious",
            "max_violations_flagged"
        ]
        set_fields = {k: float(v) if "threshold" in k else int(v) for k, v in updates.items() if k in allowed_fields}
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.settings.find_one_and_update(
            {"_id": "global_ai_config"},
            {"$set": set_fields},
            upsert=True,
            return_document=True
        )
        return self._serialize_doc(result)
