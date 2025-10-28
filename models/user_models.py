from pydantic import BaseModel

class UserResponse(BaseModel):
    """Response model for user data"""
    id: str
    email: str
    created_at: str


class UserProfile(BaseModel):
    """User profile information"""
    id: str
    email: str
    role: str
    metadata: dict = {}
