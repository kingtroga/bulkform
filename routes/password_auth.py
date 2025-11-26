from fastapi import APIRouter, HTTPException, status, Depends
from services.supabase_client import get_supabase
from services.auth import get_current_user
from models.auth_models import (
    ResetPasswordRequest, 
    UpdatePasswordRequest, 
    MessageResponse
)
import os

router = APIRouter(prefix="/api/auth", tags=["Password Management"])

# Get frontend URL from environment
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8001")


@router.post("/reset-password", response_model=MessageResponse)
async def request_password_reset(request: ResetPasswordRequest):
    """Request password reset email - ONLY for email/password users"""
    try:
        supabase = get_supabase()
        
        # Check if user exists and has a password
        # Note: Supabase doesn't expose this directly, so we just try
        supabase.auth.reset_password_for_email(
            request.email,
            options={
                "redirect_to": f"{FRONTEND_URL}/reset-password-confirm/"
            }
        )
    except Exception as e:
        # Silent fail for security
        print(f"Password reset error: {e}")
        pass
    
    return MessageResponse(
        message="If an account exists with that email, you will receive a password reset link shortly"
    )


@router.post("/set-password", response_model=MessageResponse)
async def set_initial_password(
    request: UpdatePasswordRequest,
    user: dict = Depends(get_current_user)
):
    """
    Allow OAuth users to set their first password
    This enables them to use email/password login alongside OAuth
    """
    try:
        supabase = get_supabase()
        
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        
        # Set password for user
        supabase.auth.update_user({"password": request.new_password})
        
        return MessageResponse(
            message="Password set successfully. You can now sign in with email and password."
        )
        
    except Exception as e:
        print(f"Set password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to set password"
        )


@router.post("/update-password", response_model=MessageResponse)
async def update_password(
    request: UpdatePasswordRequest,
    user: dict = Depends(get_current_user)
):
    """Update user password (requires authentication)"""
    try:
        supabase = get_supabase()
        
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        
        supabase.auth.update_user({"password": request.new_password})
        
        return MessageResponse(message="Password updated successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Password update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update password"
        )