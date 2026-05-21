"""
schemas.py — Pydantic models for request/response validation.
"""
from typing import Optional, Any
from pydantic import BaseModel


class FrameRequest(BaseModel):
    """Webcam frame sent from client for anti-cheat analysis."""
    mssv: str    # Student ID
    frame: str   # Base64-encoded JPEG image


class IdentityResult(BaseModel):
    """ArcFace face verification result."""
    status: str
    name: str
    similarity: float
    face_bbox: dict | None = None  # {x1, y1, x2, y2} normalized 0-1


class FrameResponse(BaseModel):
    """Complete analysis response for a single frame."""
    identity: IdentityResult
    head_pose: dict | None = None   # Placeholder for MediaPipe
    objects: dict | None = None     # Placeholder for YOLOv8
    alerts: list[str]
    timestamp: str


# --- User & Room Authentication / Authorization Schemas ---

class UserRegister(BaseModel):
    username: str
    password: str
    full_name: str
    role: str  # "admin", "teacher", "student"
    mssv: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    mssv: Optional[str] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class RoomCreate(BaseModel):
    room_code: str
    title: str
    description: Optional[str] = None


class RoomUpdate(BaseModel):
    title: str
    description: Optional[str] = None


class RoomResponse(BaseModel):
    id: str
    room_code: str
    title: str
    description: Optional[str] = None
    teacher_id: str
    created_at: Any

    class Config:
        from_attributes = True


class RoomStudentEnroll(BaseModel):
    room_code: str
    mssv: str


class ExamSessionStart(BaseModel):
    room_code: str


# --- AI Configuration Schemas ---
class AIConfigUpdate(BaseModel):
    face_similarity_threshold: Optional[float] = None
    head_yaw_threshold: Optional[float] = None
    head_pitch_threshold: Optional[float] = None
    yolo_confidence_threshold: Optional[float] = None
    max_violations_suspicious: Optional[int] = None
    max_violations_flagged: Optional[int] = None


class AIConfigResponse(BaseModel):
    face_similarity_threshold: float
    head_yaw_threshold: float
    head_pitch_threshold: float
    yolo_confidence_threshold: float
    max_violations_suspicious: int
    max_violations_flagged: int

