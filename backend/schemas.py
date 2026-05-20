"""
schemas.py — Pydantic models for request/response validation.
"""
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
from typing import Optional, List

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
    id: int
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


class RoomResponse(BaseModel):
    id: int
    room_code: str
    title: str
    description: Optional[str] = None
    teacher_id: int
    created_at: str

    class Config:
        from_attributes = True


class RoomStudentEnroll(BaseModel):
    room_code: str
    mssv: str


class ExamSessionStart(BaseModel):
    room_code: str

