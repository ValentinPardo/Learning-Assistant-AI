from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class UserAuth(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    
    class Config:
        from_attributes = True

class LearningGoalCreate(BaseModel):
    title: str

class LearningGoalResponse(BaseModel):
    id: int
    title: str
    user_id: int
    completed: bool
    
    class Config:
        from_attributes = True

class TaskCreate(BaseModel):
    title: str
    task_metadata: Dict[str, Any] = Field(default_factory=dict)

class TaskResponse(BaseModel):
    id: int
    title: str
    goal_id: int
    completed: bool
    task_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True

class TaskUpdateResponse(TaskResponse):
    goal_auto_completed: bool

# Schemas para autenticación
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None

# Schema para el request
class VideoProcessRequest(BaseModel):
    youtube_urls: List[str]
    webhook_url: Optional[str] = None

class VideoProcessAsyncResponse(BaseModel):
    message: str
    job_id: str
    status: ProcessingStatus
    total_videos: int
    estimated_time_minutes: int

class VideoProcessStatusResponse(BaseModel):
    job_id: str
    status: ProcessingStatus
    progress: Dict[str, Any]
    completed_videos: int
    total_videos: int
    results: List[Dict[str, Any]]
    error: Optional[str] = None
    