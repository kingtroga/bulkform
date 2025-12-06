from fastapi import APIRouter, Depends
from services.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "is_admin": user["is_admin"],  # Include admin status
        "authenticated": True
    }


@router.get("/hello")
async def hello_user(user: dict = Depends(get_current_user_optional)):
    """Optional auth example - works with or without token"""
    if user:
        return {
            "message": f"Hello {user['email']}! 👋",
            "authenticated": True,
            "is_admin": user.get("is_admin", False)
        }
    return {
        "message": "Hello! Sign in for a personalized experience.",
        "authenticated": False
    }

@router.get("/check-admin")
async def check_admin_status(current_user: dict = Depends(get_current_user)):
    """Check if current user is admin"""
    
    # Hardcoded admin emails (TEMPORARY)
    ADMIN_EMAILS = [
        "trogaclassicman@gmail.com"
    ]
    
    user_email = current_user.get("email", "").lower()
    is_admin = user_email in ADMIN_EMAILS
    
    return {
        "is_admin": is_admin,
        "user_id": current_user["id"],
        "email": user_email
    }