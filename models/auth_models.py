from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any

class SignUpRequest(BaseModel):
    """Request model for user signup"""
    email: EmailStr
    password: str
    options: Optional[Dict[str, str]] = None  

class SignInRequest(BaseModel):
    """Request model for user signin"""
    email: EmailStr
    password: str
    options: Optional[Dict[str, str]] = None  

class ResetPasswordRequest(BaseModel):
    """Request model for password reset"""
    email: EmailStr
    options: Optional[Dict[str, Any]] = None

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