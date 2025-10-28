from fastapi import APIRouter, HTTPException, status, Depends, Query
from supabase_client import get_supabase
from auth import get_current_user
from models import (
    SignUpRequest,
    SignInRequest,
    ResetPasswordRequest,
    UpdatePasswordRequest,
    RefreshTokenRequest,
    AuthResponse,
    MessageResponse
)
import os

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ============================================================================
# SIGNUP & SIGNIN
# ============================================================================

@router.post("/signup")
async def signup(credentials: SignUpRequest):
    """Sign up a new user with email/password"""
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
        
        # Check if email confirmation is required
        if not response.session:
            return MessageResponse(
                message="Account created! Please check your email to confirm your account.",
                success=True
            )
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user={
                "id": response.user.id,
                "email": response.user.email,
                "created_at": str(response.user.created_at)
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


# ============================================================================
# TOKEN MANAGEMENT
# ============================================================================

@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token"""
    try:
        supabase = get_supabase()
        response = supabase.auth.refresh_session(request.refresh_token)
        
        if not response.session or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to refresh token"
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


# ============================================================================
# PASSWORD MANAGEMENT
# ============================================================================

@router.post("/reset-password", response_model=MessageResponse)
async def request_password_reset(request: ResetPasswordRequest):
    """Request password reset email"""
    try:
        supabase = get_supabase()
        supabase.auth.reset_password_for_email(
            request.email,
            options={
                "redirect_to": "https://yourdomain.com/reset-password"  # TODO: Update this
            }
        )
    except Exception:
        pass  # Always return success
    
    return MessageResponse(
        message="If an account exists, you will receive a password reset link"
    )


@router.post("/update-password", response_model=MessageResponse)
async def update_password(
    request: UpdatePasswordRequest,
    user: dict = Depends(get_current_user)
):
    """Update user password (requires auth from reset email)"""
    try:
        supabase = get_supabase()
        supabase.auth.update_user({"password": request.new_password})
        return MessageResponse(message="Password updated successfully")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update password"
        )


# ============================================================================
# OAUTH - GOOGLE (SIMPLIFIED - LET SUPABASE HANDLE EVERYTHING)
# ============================================================================

@router.get("/google")
async def google_login():
    """
    Initiate Google OAuth - Supabase handles ALL the PKCE flow
    
    We use Supabase's built-in sign_in_with_oauth which manages:
    - PKCE generation
    - State management  
    - Code challenge/verifier pairing
    """
    try:
        supabase = get_supabase()
        
        # Let Supabase handle everything!
        response = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": os.getenv("OAUTH_CALLBACK_URL", "http://localhost:8000/api/auth/google/callback")
            }
        })
        
        print(f"✅ Generated OAuth URL via Supabase")
        
        return {
            "url": response.url,
            "provider": "google",
            "message": "Redirect user to this URL to sign in with Google"
        }
        
    except Exception as e:
        print(f"❌ Google login initiation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate Google login: {str(e)}"
        )


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None)
):
    """
    Handle Google OAuth callback
    
    Supabase already paired the code with its verifier,
    so we just need to exchange the code (no verifier needed!)
    """
    # Handle OAuth errors
    if error:
        print(f"❌ OAuth error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error_description or error}"
        )
    
    # Validate code
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code"
        )
    
    try:
        supabase = get_supabase()
        
        print(f"🔄 Exchanging code for session (Supabase handles verifier)...")
        
        # Just pass the code - Supabase retrieves its own stored verifier
        response = supabase.auth.exchange_code_for_session({
            "auth_code": code
        })
        
        if not response or not hasattr(response, 'session') or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange code for session"
            )
        
        print(f"✅ Session created for user: {response.user.email}")
        
        # Extract user information safely
        user_metadata = getattr(response.user, 'user_metadata', {}) or {}
        
        # Return complete auth response
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "expires_in": getattr(response.session, 'expires_in', 3600),
            "token_type": "bearer",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "name": user_metadata.get("full_name") or user_metadata.get("name", ""),
                "avatar": user_metadata.get("avatar_url") or user_metadata.get("picture", ""),
                "email_verified": getattr(response.user, 'email_confirmed_at', None) is not None
            },
            "message": "✅ Google authentication successful!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Google callback error: {str(e)}")
        print(error_trace)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


@router.get("/google/debug")
async def google_debug():
    """Debug endpoint to check Supabase configuration"""
    try:
        supabase = get_supabase()
        
        return {
            "supabase_url": os.getenv("SUPABASE_URL"),
            "supabase_key_present": bool(os.getenv("SUPABASE_KEY")),
            "oauth_callback_url": os.getenv("OAUTH_CALLBACK_URL", "http://localhost:8000/api/auth/google/callback"),
            "library_info": {
                "client_type": str(type(supabase)),
                "has_exchange_method": hasattr(supabase.auth, 'exchange_code_for_session'),
                "has_oauth_method": hasattr(supabase.auth, 'sign_in_with_oauth')
            }
        }
    except Exception as e:
        return {"error": str(e)}