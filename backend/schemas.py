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
