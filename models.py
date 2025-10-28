from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# ============================================================================
# AUTH MODELS
# ============================================================================

class SignUpRequest(BaseModel):
    """Request model for user signup"""
    email: EmailStr
    password: str

class SignInRequest(BaseModel):
    """Request model for user signin"""
    email: EmailStr
    password: str

class ResetPasswordRequest(BaseModel):
    """Request model for password reset"""
    email: EmailStr

class UpdatePasswordRequest(BaseModel):
    """Request model for password update"""
    new_password: str

class RefreshTokenRequest(BaseModel):
    """Request model for token refresh"""
    refresh_token: str

class AuthResponse(BaseModel):
    """Response model for successful authentication"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True

# ============================================================================
# USER MODELS
# ============================================================================

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

# ============================================================================
# PROFILE MODELS
# ============================================================================

class ProfileBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    
class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: str
    role: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ============================================================================
# TODO: Add more models as you build features
# ============================================================================

# class PDFUploadRequest(BaseModel):
#     """Request model for PDF upload"""
#     pass

# class TemplateCreateRequest(BaseModel):
#     """Request model for template creation"""
#     pass