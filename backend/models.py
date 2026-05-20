"""
models.py — SQLAlchemy database models representing the tables:
Users, ExamRooms, RoomStudents, ExamSessions, and ViolationLogs.
"""
from datetime import datetime
import json
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    """
    Represents users in the system (Admin, Teacher, Student).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(50), nullable=False)  # "admin", "teacher", "student"
    full_name = Column(String(150), nullable=False)
    mssv = Column(String(50), unique=True, index=True, nullable=True)  # Nullable for teachers/admins
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    created_rooms = relationship("ExamRoom", back_populates="teacher")
    room_enrollments = relationship("RoomStudent", back_populates="student")
    exam_sessions = relationship("ExamSession", back_populates="student")
    violations = relationship("ViolationLog", back_populates="student")


class ExamRoom(Base):
    """
    Represents exam rooms created by teachers.
    """
    __tablename__ = "exam_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="created_rooms")
    students = relationship("RoomStudent", back_populates="room", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="room", cascade="all, delete-orphan")
    violations = relationship("ViolationLog", back_populates="room", cascade="all, delete-orphan")


class RoomStudent(Base):
    """
    Association table representing student enrollment in rooms,
    and storing their registered face descriptor (embedding) & image.
    """
    __tablename__ = "room_students"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("exam_rooms.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    face_embedding = Column(Text, nullable=True)  # JSON-serialized list of 512 floats
    face_image_path = Column(String(500), nullable=True)  # Path to saved anchor image
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    room = relationship("ExamRoom", back_populates="students")
    student = relationship("User", back_populates="room_enrollments")

    def get_embedding(self) -> list[float] | None:
        """Helper to deserialize face embedding JSON back to a list."""
        if self.face_embedding:
            try:
                return json.loads(self.face_embedding)
            except Exception:
                return None
        return None

    def set_embedding(self, embedding_list: list[float]):
        """Helper to serialize face embedding list into JSON string."""
        if embedding_list is not None:
            # Convert numpy array to list if needed
            if hasattr(embedding_list, "tolist"):
                embedding_list = embedding_list.tolist()
            self.face_embedding = json.dumps(embedding_list)
        else:
            self.face_embedding = None


class ExamSession(Base):
    """
    Tracks a student's active/past exam attempt within a specific room.
    Integrates warning count escalation.
    """
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("exam_rooms.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    violation_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="NORMAL", nullable=False)  # "NORMAL", "SUSPICIOUS", "FLAGGED"

    # Relationships
    room = relationship("ExamRoom", back_populates="sessions")
    student = relationship("User", back_populates="exam_sessions")
    violations = relationship("ViolationLog", back_populates="session", cascade="all, delete-orphan")


class ViolationLog(Base):
    """
    Detailed audit log of cheating violations flagged by the AI engine.
    """
    __tablename__ = "violation_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=True)
    room_id = Column(Integer, ForeignKey("exam_rooms.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    violation_type = Column(String(100), nullable=False)  # "cell_phone", "unknown_person", "no_face", "multiple_persons", etc.
    severity = Column(String(50), nullable=False)  # "CRITICAL", "WARNING"
    similarity_score = Column(Float, nullable=True)
    details = Column(Text, nullable=False)
    frame_image_path = Column(String(500), nullable=True)  # Path to saved screenshot of violation

    # Relationships
    session = relationship("ExamSession", back_populates="violations")
    room = relationship("ExamRoom", back_populates="violations")
    student = relationship("User", back_populates="violations")
