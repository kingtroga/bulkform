from fastapi import APIRouter, HTTPException, status, Depends
from supabase_client import get_supabase
from auth import get_current_user
from models import ResetPasswordRequest, UpdatePasswordRequest, MessageResponse

router = APIRouter(prefix="/api/auth", tags=["Password Management"])


@router.post("/reset-password", response_model=MessageResponse)
async def request_password_reset(request: ResetPasswordRequest):
    """Request password reset email"""
    try:
        supabase = get_supabase()
        supabase.auth.reset_password_for_email(
            request.email,
            options={
                "redirect_to": "https://yourdomain.com/reset-password"  # TODO: Update
            }
        )
    except Exception:
        pass
    
    return MessageResponse(
        message="If an account exists, you will receive a password reset link"
    )


@router.post("/update-password", response_model=MessageResponse)
async def update_password(
    request: UpdatePasswordRequest,
    user: dict = Depends(get_current_user)
):
    """Update user password (requires authentication)"""
    try:
        supabase = get_supabase()
        supabase.auth.update_user({"password": request.new_password})
        return MessageResponse(message="Password updated successfully")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update password"
        )