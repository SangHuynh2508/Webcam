"""
db_init.py — Database initialization script.
Creates tables and seeds default Admin, Teacher, and Student accounts,
as well as a sample exam room and student enrollment.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine, Base
from backend.models import User, ExamRoom, RoomStudent
from backend.auth import get_password_hash

def init_db():
    print("🔄 Đang khởi tạo các bảng cơ sở dữ liệu SQLite...")
    Base.metadata.create_all(bind=engine)
    print("✅ Các bảng đã được khởi tạo thành công.")

    db: Session = SessionLocal()
    try:
        print("🌱 Đang kiểm tra dữ liệu mẫu (seeding)...")
        
        # 1. Seed Users
        # Admin
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                role="admin",
                full_name="Quản trị viên Hệ thống"
            )
            db.add(admin_user)
            print("  ➕ Đã thêm tài khoản Admin (admin/admin123)")
        
        # Teacher
        teacher_user = db.query(User).filter(User.username == "gv_quang").first()
        if not teacher_user:
            teacher_user = User(
                username="gv_quang",
                hashed_password=get_password_hash("teacher123"),
                role="teacher",
                full_name="Thầy Vũ Duy Quang"
            )
            db.add(teacher_user)
            print("  ➕ Đã thêm tài khoản Giáo viên (gv_quang/teacher123)")
            
        # Student (mapped to existing anchor photo 2380601889_HuynhMinhSang.jpg)
        student_user = db.query(User).filter(User.username == "sv_sang").first()
        if not student_user:
            student_user = User(
                username="sv_sang",
                hashed_password=get_password_hash("student123"),
                role="student",
                full_name="Huỳnh Minh Sáng",
                mssv="2380601889"
            )
            db.add(student_user)
            print("  ➕ Đã thêm tài khoản Sinh viên (sv_sang/student123, MSSV: 2380601889)")
            
        db.commit()
        db.refresh(teacher_user)
        db.refresh(student_user)

        # 2. Seed Exam Rooms
        room101 = db.query(ExamRoom).filter(ExamRoom.room_code == "ROOM_101").first()
        if not room101:
            room101 = ExamRoom(
                room_code="ROOM_101",
                title="Phòng thi Cơ sở dữ liệu",
                description="Kỳ thi lý thuyết cuối kỳ môn Cơ sở dữ liệu đại cương.",
                teacher_id=teacher_user.id
            )
            db.add(room101)
            print("  ➕ Đã thêm phòng thi ROOM_101")

        room102 = db.query(ExamRoom).filter(ExamRoom.room_code == "ROOM_102").first()
        if not room102:
            room102 = ExamRoom(
                room_code="ROOM_102",
                title="Phòng thi Trí tuệ nhân tạo",
                description="Kỳ thi thực hành môn Trí tuệ nhân tạo nâng cao.",
                teacher_id=teacher_user.id
            )
            db.add(room102)
            print("  ➕ Đã thêm phòng thi ROOM_102")
            
        db.commit()
        db.refresh(room101)

        # 3. Seed Student Enrollment (Huynh Minh Sang into ROOM_101)
        enrollment = db.query(RoomStudent).filter(
            RoomStudent.room_id == room101.id,
            RoomStudent.student_id == student_user.id
        ).first()
        
        if not enrollment:
            # We can save face descriptor embedding as null or we can load it later
            enrollment = RoomStudent(
                room_id=room101.id,
                student_id=student_user.id,
                face_image_path="data/anchor/2380601889_HuynhMinhSang.jpg"
            )
            db.add(enrollment)
            print(f"  ➕ Đã ghi danh Sinh viên '{student_user.full_name}' vào phòng '{room101.title}'")
            
        db.commit()
        print("🎉 Seed dữ liệu mẫu hoàn thành!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Lỗi khi seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
