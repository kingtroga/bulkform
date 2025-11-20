"""
Authentication utilities
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import os
from typing import Optional
from services.supabase_client import get_supabase

# Security scheme
security = HTTPBearer()

# Get JWT secret from Supabase (this is your anon key for now)
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", os.getenv("SUPABASE_KEY"))
ADMIN_EMAILS = [
    "trogaclassicman@gmail.com", 
]

def verify_token(token: str) -> dict:
    """
    Verify Supabase JWT token
    Returns user data if valid, raises HTTPException if invalid
    """
    try:
        # Decode JWT token
        payload = jwt.decode(
            token, 
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False} # Supabase tokens don't have aud claim
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def is_admin_user(email: str) -> bool:
    """
    Check if user is admin based on email
    """
    return email in ADMIN_EMAILS
    
async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to get current authenticated user
    Use this in your endpoints: user = Depends(get_current_user)
    """
    token = credentials.credentials
    user_data = verify_token(token)

    # Extract user ID from token
    user_id = user_data.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID"
        )
    
    email = user_data.get("email")
    
    return {
        "id": user_id,
        "email": email,
        "role": user_data.get("role", "user"),
        "metadata": user_data.get("user_metadata", {}),
        "is_admin": is_admin_user(email)  # Add admin check
    }

async def get_current_user_optional(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[dict]:
    """
    Optional authentication - returns None if no token provided
    Use for endpoints that work both with/without auth
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require admin user
    Use this for admin-only endpoints
    """
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user