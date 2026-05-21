"""
setup.py — MongoDB Schema Validation, Indexing, and Database Seeding Script.
Executes MongoDB setup by applying strict JSON Schema validations ($jsonSchema),
creating performance indexes, and seeding default Admin, Teacher, and Student accounts.
"""
import os
import sys
from datetime import datetime
from pymongo import MongoClient, errors

# Add project root directory to path to allow absolute backend.* imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.auth import get_password_hash  # noqa: E402

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "anti_cheat_db")

_original_print = print
def safe_print(*args, **kwargs):
    try:
        _original_print(*args, **kwargs)
    except UnicodeEncodeError:
        new_args = []
        for arg in args:
            if isinstance(arg, str):
                new_args.append(arg.encode('ascii', 'replace').decode('ascii'))
            else:
                new_args.append(arg)
        try:
            _original_print(*new_args, **kwargs)
        except Exception:
            pass

print = safe_print

def create_validations_and_indexes(db, drop_existing=True):
    print("✨ --- 1. THIẾT LẬP CƠ SỞ DỮ LIỆU MONGODB ---")
    
    # ------------------------------------------------------------------
    # Collection: users
    # ------------------------------------------------------------------
    print("👤 Đang thiết lập collection 'users'...")
    if drop_existing and "users" in db.list_collection_names():
        db.drop_collection("users")
    
    user_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["username", "hashed_password", "role", "full_name", "created_at"],
            "properties": {
                "username": {
                    "bsonType": "string",
                    "description": "Tên đăng nhập bắt buộc phải là một chuỗi"
                },
                "hashed_password": {
                    "bsonType": "string",
                    "description": "Mật khẩu mã hóa bcrypt bắt buộc phải là chuỗi"
                },
                "role": {
                    "enum": ["admin", "teacher", "student"],
                    "description": "Vai trò phải nằm trong các giá trị: admin, teacher, student"
                },
                "full_name": {
                    "bsonType": "string",
                    "description": "Họ và tên bắt buộc phải là chuỗi"
                },
                "mssv": {
                    "bsonType": ["string", "null"],
                    "description": "Mã số sinh viên (chỉ dành cho student, có thể null)"
                },
                "created_at": {
                    "bsonType": "date",
                    "description": "Ngày tạo bắt buộc phải thuộc kiểu date"
                }
            }
        }
    }
    
    if "users" not in db.list_collection_names():
        db.create_collection("users", validator=user_validator)
    else:
        db.command("collMod", "users", validator=user_validator)

    db["users"].create_index("username", unique=True)
    db["users"].create_index("mssv", unique=True, sparse=True)
    print("  ✅ Tạo thành công users collection, validators và unique indexes.")

    # ------------------------------------------------------------------
    # Collection: exam_rooms
    # ------------------------------------------------------------------
    print("🏫 Đang thiết lập collection 'exam_rooms'...")
    if drop_existing and "exam_rooms" in db.list_collection_names():
        db.drop_collection("exam_rooms")

    room_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["room_code", "title", "teacher_id", "students", "created_at"],
            "properties": {
                "room_code": {
                    "bsonType": "string",
                    "description": "Mã phòng thi bắt buộc là chuỗi"
                },
                "title": {
                    "bsonType": "string",
                    "description": "Tiêu đề phòng thi bắt buộc là chuỗi"
                },
                "description": {
                    "bsonType": ["string", "null"],
                    "description": "Mô tả phòng thi có thể là chuỗi hoặc null"
                },
                "teacher_id": {
                    "bsonType": "objectId",
                    "description": "ID giáo viên tạo phòng thi (ObjectId từ users)"
                },
                "students": {
                    "bsonType": "array",
                    "description": "Danh sách sinh viên ghi danh trong phòng thi",
                    "items": {
                        "bsonType": "object",
                        "required": ["student_id", "enrolled_at"],
                        "properties": {
                            "student_id": {
                                "bsonType": "objectId",
                                "description": "ID sinh viên (ObjectId từ users)"
                            },
                            "face_embedding": {
                                "bsonType": ["array", "null"],
                                "description": "Vector nhúng 512 số thực của khuôn mặt sinh viên",
                                "items": {
                                    "bsonType": "double"
                                }
                            },
                            "face_image_path": {
                                "bsonType": ["string", "null"],
                                "description": "Đường dẫn file ảnh anchor"
                            },
                            "enrolled_at": {
                                "bsonType": "date"
                            }
                        }
                    }
                },
                "created_at": {
                    "bsonType": "date"
                }
            }
        }
    }

    if "exam_rooms" not in db.list_collection_names():
        db.create_collection("exam_rooms", validator=room_validator)
    else:
        db.command("collMod", "exam_rooms", validator=room_validator)

    db["exam_rooms"].create_index("room_code", unique=True)
    db["exam_rooms"].create_index("students.student_id")
    print("  ✅ Tạo thành công exam_rooms với embedded students array và indexes.")

    # ------------------------------------------------------------------
    # Collection: exam_sessions
    # ------------------------------------------------------------------
    print("⏱️ Đang thiết lập collection 'exam_sessions'...")
    if drop_existing and "exam_sessions" in db.list_collection_names():
        db.drop_collection("exam_sessions")

    session_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["room_id", "student_id", "started_at", "violation_count", "status"],
            "properties": {
                "room_id": {
                    "bsonType": "objectId",
                    "description": "ID phòng thi"
                },
                "student_id": {
                    "bsonType": "objectId",
                    "description": "ID sinh viên làm bài"
                },
                "started_at": {
                    "bsonType": "date"
                },
                "ended_at": {
                    "bsonType": ["date", "null"]
                },
                "violation_count": {
                    "bsonType": "int",
                    "minimum": 0
                },
                "status": {
                    "enum": ["NORMAL", "SUSPICIOUS", "FLAGGED"]
                }
            }
        }
    }

    if "exam_sessions" not in db.list_collection_names():
        db.create_collection("exam_sessions", validator=session_validator)
    else:
        db.command("collMod", "exam_sessions", validator=session_validator)

    db["exam_sessions"].create_index([("student_id", 1), ("ended_at", 1)])
    db["exam_sessions"].create_index([("room_id", 1), ("ended_at", 1)])
    print("  ✅ Tạo thành công exam_sessions và compound indexes.")

    # ------------------------------------------------------------------
    # Collection: violation_logs
    # ------------------------------------------------------------------
    print("🚨 Đang thiết lập collection 'violation_logs'...")
    if drop_existing and "violation_logs" in db.list_collection_names():
        db.drop_collection("violation_logs")

    log_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["session_id", "room_id", "student_id", "timestamp", "violation_type", "severity", "details"],
            "properties": {
                "session_id": {
                    "bsonType": "objectId"
                },
                "room_id": {
                    "bsonType": "objectId"
                },
                "student_id": {
                    "bsonType": "objectId"
                },
                "timestamp": {
                    "bsonType": "date"
                },
                "violation_type": {
                    "bsonType": "string"
                },
                "severity": {
                    "enum": ["CRITICAL", "WARNING"]
                },
                "similarity_score": {
                    "bsonType": ["double", "null"]
                },
                "details": {
                    "bsonType": "string"
                },
                "frame_image_path": {
                    "bsonType": ["string", "null"]
                }
            }
        }
    }

    if "violation_logs" not in db.list_collection_names():
        db.create_collection("violation_logs", validator=log_validator)
    else:
        db.command("collMod", "violation_logs", validator=log_validator)

    db["violation_logs"].create_index([("session_id", 1), ("timestamp", -1)])
    db["violation_logs"].create_index("student_id")
    db["violation_logs"].create_index("room_id")
    print("  ✅ Tạo thành công violation_logs và indexes cho truy xuất thời gian thực.")

    # ------------------------------------------------------------------
    # Collection: system_settings
    # ------------------------------------------------------------------
    print("⚙️ Đang thiết lập collection 'system_settings'...")
    if drop_existing and "system_settings" in db.list_collection_names():
        db.drop_collection("system_settings")

    settings_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "face_similarity_threshold", 
                "head_yaw_threshold", 
                "head_pitch_threshold", 
                "yolo_confidence_threshold", 
                "max_violations_suspicious", 
                "max_violations_flagged", 
                "updated_at"
            ],
            "properties": {
                "face_similarity_threshold": {"bsonType": "double"},
                "head_yaw_threshold": {"bsonType": "double"},
                "head_pitch_threshold": {"bsonType": "double"},
                "yolo_confidence_threshold": {"bsonType": "double"},
                "max_violations_suspicious": {"bsonType": "int"},
                "max_violations_flagged": {"bsonType": "int"},
                "updated_at": {"bsonType": "date"}
            }
        }
    }

    if "system_settings" not in db.list_collection_names():
        db.create_collection("system_settings", validator=settings_validator)
    else:
        db.command("collMod", "system_settings", validator=settings_validator)
    print("  ✅ Tạo thành công system_settings để lưu trữ cấu hình ngưỡng AI động.")


def seed_database(db):
    print("\n🌱 --- 2. DỮ LIỆU SEED MẪU (SEEDING) ---")
    
    # 1. Seeds Users
    # Admin
    admin_doc = {
        "username": "admin",
        "hashed_password": get_password_hash("admin123"),
        "role": "admin",
        "full_name": "Quản trị viên Hệ thống",
        "created_at": datetime.utcnow()
    }
    admin_id = db["users"].insert_one(admin_doc).inserted_id
    print(f"  ➕ Đã thêm tài khoản Admin (admin/admin123) -> ID: {admin_id}")

    # Teacher
    teacher_doc = {
        "username": "gv_quang",
        "hashed_password": get_password_hash("teacher123"),
        "role": "teacher",
        "full_name": "Thầy Vũ Duy Quang",
        "created_at": datetime.utcnow()
    }
    teacher_id = db["users"].insert_one(teacher_doc).inserted_id
    print(f"  ➕ Đã thêm tài khoản Giáo viên (gv_quang/teacher123) -> ID: {teacher_id}")

    # Student
    student_doc = {
        "username": "sv_sang",
        "hashed_password": get_password_hash("student123"),
        "role": "student",
        "full_name": "Huỳnh Minh Sang",
        "mssv": "2380601889",
        "created_at": datetime.utcnow()
    }
    student_id = db["users"].insert_one(student_doc).inserted_id
    print(f"  ➕ Đã thêm tài khoản Sinh viên (sv_sang/student123, MSSV: 2380601889) -> ID: {student_id}")

    # 2. Seeds Rooms (Removed mock rooms per user request)
    
    # 3. Seed Global system thresholds settings
    settings_doc = {
        "_id": "global_ai_config",
        "face_similarity_threshold": 0.55,
        "head_yaw_threshold": 30.0,
        "head_pitch_threshold": 25.0,
        "yolo_confidence_threshold": 0.65,
        "max_violations_suspicious": 3,
        "max_violations_flagged": 5,
        "updated_at": datetime.utcnow()
    }
    db["system_settings"].insert_one(settings_doc)
    print("  ➕ Đã lưu trữ cấu hình ngưỡng AI mặc định (global_ai_config)")
    
    print("\n🎉 Seed dữ liệu mẫu MongoDB thành công hoàn tất!")


def run_setup(drop_existing=False):
    print(f"🔗 Đang kết nối tới máy chủ MongoDB: {MONGODB_URI}...")
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        client.server_info()
        db = client[DB_NAME]
        
        create_validations_and_indexes(db, drop_existing=drop_existing)
        
        # Check if users collection is empty before seeding
        if db["users"].count_documents({}) == 0:
            seed_database(db)
        else:
            print("\n⚠️ Database đã có dữ liệu. Bỏ qua bước seed dữ liệu mặc định.")
            
    except errors.ServerSelectionTimeoutError:
        print("\n❌ LỖI KẾT NỐI: Không thể kết nối tới máy chủ MongoDB!")
        print("  - Vui lòng kiểm tra xem MongoDB đã khởi chạy ở cổng localhost:27017 hay chưa.")
        print("  - Hoặc cấu hình biến môi trường MONGODB_URI.")
        return False
    except Exception as e:
        print(f"\n❌ LỖI NGOẠI LỆ TRONG QUÁ TRÌNH SETUP: {e}")
        return False
    return True


if __name__ == "__main__":
    # If run as script directly, we can default drop_existing=True to reset database
    run_setup(drop_existing=True)
