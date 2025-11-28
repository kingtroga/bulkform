from fastapi import APIRouter, HTTPException, status, Depends, Header
from services.supabase_client import get_supabase
from services.auth import get_current_user
from models.auth_models import (
    ResetPasswordRequest, 
    UpdatePasswordRequest, 
    MessageResponse
)
import os

router = APIRouter(prefix="/api/auth", tags=["Password Management"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8001")


@router.post("/reset-password", response_model=MessageResponse)
async def request_password_reset(request: ResetPasswordRequest):
    """Request password reset email"""
    try:
        supabase = get_supabase()

        # Extract captcha token if provided
        captcha_token = None
        if request.options:
            captcha_token = request.options.get("captchaToken")

        options = {
            "redirect_to": f"{FRONTEND_URL}/reset-password-confirm/"
        }
        if captcha_token:
            options["captchaToken"] = captcha_token

        supabase.auth.reset_password_for_email(
            request.email,
            options=options
        )

    except Exception as e:
        # Supabase will throw here if captcha is missing/invalid, email not allowed, etc.
        print(f"Password reset error: {e}")
        # We still return generic message to avoid leaking which emails exist

    return MessageResponse(
        message="If an account exists with that email, you will receive a password reset link shortly"
    )



@router.post("/update-password", response_model=MessageResponse)
async def update_password(
    request: UpdatePasswordRequest,
    authorization: str = Header(None)
):
    """
    Update user password using token from password reset email
    This endpoint works with the token from the reset link
    """
    try:
        # Extract token from Authorization header
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No authorization token provided"
            )
        
        # Remove "Bearer " prefix if present
        token = authorization.replace("Bearer ", "").strip()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token"
            )
        
        print(f"Updating password with token: {token[:20]}...") # Debug
        
        # Validate password
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )
        
        # Create a new Supabase client with the provided token
        supabase = get_supabase()
        
        # Set the session with the token from the reset link
        supabase.auth.set_session(token, token)  # Use token as both access and refresh
        
        # Update password
        response = supabase.auth.update_user({"password": request.new_password})
        
        print(f"Password update response: {response}") # Debug
        
        return MessageResponse(message="Password updated successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Password update error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update password: {str(e)}"
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