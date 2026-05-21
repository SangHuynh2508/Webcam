"""
test_mongodb_crud.py — MongoDB Repository Async Integration Tests.
Executes testing on MongoDBRepository async methods (User, Room, Session, Logs, and AI Settings).
"""
import os
import sys
import asyncio

# Add project root directory to path to allow absolute backend.* imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.database.mongodb import MongoDBRepository  # noqa: E402
from backend.database.setup import run_setup  # noqa: E402

# Test configuration
TEST_DB_NAME = "anti_cheat_db_test"

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

async def run_tests():
    print("🚀 --- BẮT ĐẦU BÀI KIỂM THỬ TÍCH HỢP MONGODB REPOSITORY ---")
    
    # 1. Setup test database collections, schemas, indexes
    print("\n📦 1. Thiết lập Cấu hình Schema & Indexes trên DB test...")
    os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME
    run_setup(drop_existing=True)
    
    repo = MongoDBRepository(db_name=TEST_DB_NAME)
    
    success = True
    try:
        # 2. Test User Management
        print("\n👤 2. Kiểm thử Quản lý Người dùng (User)...")
        # Register teacher
        teacher = await repo.register_user(
            username="test_gv",
            password_plain="gv_pass123",
            role="teacher",
            full_name="Giáo Viên Kiểm Thử"
        )
        assert teacher["username"] == "test_gv"
        assert teacher["role"] == "teacher"
        print("  ✅ Đăng ký giáo viên thành công.")

        # Register student
        student = await repo.register_user(
            username="test_sv",
            password_plain="sv_pass123",
            role="student",
            full_name="Sinh Viên Kiểm Thử",
            mssv="TEST9999"
        )
        assert student["mssv"] == "TEST9999"
        assert student["role"] == "student"
        print("  ✅ Đăng ký sinh viên thành công.")

        # Authenticate
        auth_user = await repo.authenticate_user("test_gv", "gv_pass123")
        assert auth_user is not None
        assert auth_user["id"] == teacher["id"]
        
        bad_auth = await repo.authenticate_user("test_gv", "wrong_pass")
        assert bad_auth is None
        print("  ✅ Xác thực thông tin đăng nhập thành công.")

        # Get by username & ID
        u_by_name = await repo.get_user_by_username("test_sv")
        assert u_by_name["id"] == student["id"]
        
        u_by_id = await repo.get_user_by_id(student["id"])
        assert u_by_id["username"] == "test_sv"
        print("  ✅ Các truy vấn tìm kiếm (Get User) thành công.")

        # Update User
        updated_user = await repo.update_user("test_sv", {"full_name": "Sinh Viên Đã Đổi Tên"})
        assert updated_user["full_name"] == "Sinh Viên Đã Đổi Tên"
        print("  ✅ Cập nhật thông tin người dùng thành công.")

        # 3. Test Room Operations
        print("\n🏫 3. Kiểm thử Quản lý Phòng Thi (Room)...")
        room = await repo.create_room(
            room_code="TEST_ROOM",
            title="Lớp kiểm thử",
            description="Phòng thi thử nghiệm",
            teacher_id=teacher["id"]
        )
        assert room["room_code"] == "TEST_ROOM"
        assert room["teacher_id"] == teacher["id"]
        print("  ✅ Tạo phòng thi thành công.")

        # Get room details
        room_by_code = await repo.get_room_by_code("TEST_ROOM")
        assert room_by_code["id"] == room["id"]
        print("  ✅ Tìm kiếm phòng thi bằng mã (room_code) thành công.")

        # Update Room
        updated_room = await repo.update_room("TEST_ROOM", "Lớp kiểm thử nâng cao", "Mô tả mới")
        assert updated_room["title"] == "Lớp kiểm thử nâng cao"
        assert updated_room["description"] == "Mô tả mới"
        print("  ✅ Cập nhật thông tin phòng thi thành công.")

        # Enroll Student
        enroll_res = await repo.enroll_student("TEST_ROOM", "TEST9999", "/test/image.jpg")
        assert enroll_res["status"] == "ok"
        print("  ✅ Ghi danh sinh viên vào phòng thi thành công.")

        # Check enrolled students list
        students_list = await repo.get_room_students("TEST_ROOM")
        assert len(students_list) == 1
        assert students_list[0]["mssv"] == "TEST9999"
        assert students_list[0]["has_face_registered"] is True
        print("  ✅ Truy vấn danh sách sinh viên trong phòng thi thành công.")

        # Get room anchors list (new method)
        anchors = await repo.get_room_anchors("TEST_ROOM")
        assert len(anchors) == 1
        assert anchors[0]["mssv"] == "TEST9999"
        assert anchors[0]["face_image_path"] == "/test/image.jpg"
        print("  ✅ Truy vấn anchors ảnh khuôn mặt trong phòng thi thành công.")

        # Update Face Embedding
        face_updated = await repo.update_student_face_data("TEST9999", [0.1, 0.2, 0.3], "/test/new_image.jpg")
        assert face_updated is True
        
        # Verify face embedding updated in anchors
        anchors_updated = await repo.get_room_anchors("TEST_ROOM")
        assert anchors_updated[0]["embedding"] == [0.1, 0.2, 0.3]
        assert anchors_updated[0]["face_image_path"] == "/test/new_image.jpg"
        print("  ✅ Cập nhật vector nhúng (face embedding) của sinh viên thành công.")

        # 4. Test Session Operations
        print("\n⏱️ 4. Kiểm thử Phiên thi & Giám sát (Session)...")
        # Start session
        session = await repo.start_exam_session("TEST_ROOM", student["id"])
        assert session["room_id"] == room["id"]
        assert session["student_id"] == student["id"]
        assert session["status"] == "NORMAL"
        print("  ✅ Bắt đầu phiên thi (start session) thành công.")

        # Get live status
        live_status = await repo.get_room_live_status("TEST_ROOM")
        assert live_status["room_code"] == "TEST_ROOM"
        assert len(live_status["students"]) == 1
        assert live_status["students"][0]["is_active"] is True
        assert live_status["students"][0]["status"] == "NORMAL"
        print("  ✅ Truy vấn trạng thái giám sát trực tiếp (live status) thành công.")

        # 5. Test Violation Logging & Settings
        print("\n🚨 5. Kiểm thử Cảnh báo Vi phạm & Cấu hình AI (Violations & Settings)...")
        # Log critical violation
        log_res = await repo.log_violation(
            session_id=session["id"],
            room_id=room["id"],
            student_id=student["id"],
            violation_type="cell_phone",
            severity="CRITICAL",
            similarity_score=0.92,
            details="Phát hiện điện thoại di động",
            frame_image_path="/test/violation_frame.jpg"
        )
        assert log_res["violation_type"] == "cell_phone"
        assert log_res["severity"] == "CRITICAL"
        print("  ✅ Ghi log vi phạm (log violation) thành công.")

        # Check violation count escalated
        from bson import ObjectId
        active_sess = await repo.sessions.find_one({"_id": ObjectId(session["id"])})
        assert active_sess["violation_count"] == 1
        print("  ✅ Hệ thống đếm dồn số lần vi phạm thành công.")

        # Check get_violation_logs
        v_logs = await repo.get_violation_logs(room_code="TEST_ROOM", mssv="TEST9999")
        assert len(v_logs) == 1
        assert v_logs[0]["violation_type"] == "cell_phone"
        assert v_logs[0]["id"] == str(log_res["_id"])
        print("  ✅ Truy vấn danh sách vi phạm (filters) thành công.")

        # Check get_violation_log_by_id
        v_by_id = await repo.get_violation_log_by_id(str(log_res["_id"]))
        assert v_by_id["violation_type"] == "cell_phone"
        print("  ✅ Tìm kiếm log vi phạm cụ thể bằng ID thành công.")

        # Check get and update AI settings
        default_settings = await repo.get_system_settings()
        assert default_settings["face_similarity_threshold"] == 0.55
        
        updated_settings = await repo.update_system_settings({"face_similarity_threshold": 0.62})
        assert updated_settings["face_similarity_threshold"] == 0.62
        print("  ✅ Truy vấn và cấu hình cài đặt AI động thành công.")

        # Submit Session
        submitted = await repo.submit_exam_session(student["id"])
        assert submitted is True
        
        live_status_after = await repo.get_room_live_status("TEST_ROOM")
        assert live_status_after["students"][0]["is_active"] is False
        print("  ✅ Nộp bài thi và kết thúc phiên thi (submit session) thành công.")

        # 6. Test Cascade Delete
        print("\n🗑️ 6. Kiểm thử Hủy Ghi danh & Xóa Phòng Thi (Cascade)...")
        # Unenroll Student
        unenroll_ok = await repo.unenroll_student("TEST_ROOM", "TEST9999")
        assert unenroll_ok is True
        
        students_empty = await repo.get_room_students("TEST_ROOM")
        assert len(students_empty) == 0
        print("  ✅ Hủy ghi danh sinh viên (unenroll) thành công.")

        # Delete Room
        deleted_ok = await repo.delete_room("TEST_ROOM")
        assert deleted_ok is True
        
        room_deleted = await repo.get_room_by_code("TEST_ROOM")
        assert room_deleted is None
        
        # Verify cascaded sessions and logs deleted
        sess_count = await repo.sessions.count_documents({"room_id": room["_id"]})
        logs_count = await repo.logs.count_documents({"room_id": room["_id"]})
        assert sess_count == 0
        assert logs_count == 0
        print("  ✅ Xóa phòng thi và các liên kết phụ thuộc (Cascade Delete) thành công.")

        # Delete User
        user_deleted = await repo.delete_user("test_sv")
        assert user_deleted is True
        print("  ✅ Xóa người dùng thành công.")

        print("\n🏆 --- TẤT CẢ CÁC BÀI KIỂM THỬ THÀNH CÔNG RỰC RỠ! ---")
        
    except AssertionError:
        print("\n❌ KIỂM THỬ THẤT BẠI: Assertion failed.")
        import traceback
        traceback.print_exc()
        success = False
    except Exception as e:
        print(f"\n❌ LỖI NGOẠI LỆ KHI KIỂM THỬ: {e}")
        import traceback
        traceback.print_exc()
        success = False
    finally:
        # Clean up database
        print("\n🧹 Đang xóa dọn cơ sở dữ liệu kiểm thử...")
        await repo.client.drop_database(TEST_DB_NAME)
        print("  ✅ Đã xóa cơ sở dữ liệu test.")
        
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_tests())
