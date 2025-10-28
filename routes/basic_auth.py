from fastapi import APIRouter, HTTPException, status, Depends
from supabase_client import get_supabase
from auth import get_current_user
from models import SignUpRequest, SignInRequest, AuthResponse, MessageResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/signup")
async def signup(credentials: SignUpRequest):
    try:
        supabase = get_supabase()
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        # Profile is auto-created by trigger, fetch it
        profile = supabase.table("profiles").select("*").eq("id", response.user.id).single().execute()
        
        if not response.session:
            return MessageResponse(
                message="Account created! Please check your email to confirm.",
                success=True
            )
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user=profile.data if profile.data else {
                "id": response.user.id,
                "email": response.user.email
            }
        )
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )


@router.post("/signin", response_model=AuthResponse)
async def signin(credentials: SignInRequest):
    """Sign in with email/password"""
    try: 
        supabase = get_supabase()
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })

        if not response.user or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user={
                "id": response.user.id,
                "email": response.user.email
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        if "email not confirmed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please confirm your email before signing in"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


@router.post("/signout", response_model=MessageResponse)
async def signout(user: dict = Depends(get_current_user)):
    """Sign out current user"""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
        return MessageResponse(message="Successfully signed out")
    except Exception:
        return MessageResponse(message="Signed out", success=True)