from fastapi import APIRouter, HTTPException, status, Query
from services.supabase_client import get_supabase
import os

router = APIRouter(prefix="/api/auth/google", tags=["OAuth - Google"])


@router.get("")
async def google_login():
    """Initiate Google OAuth login"""
    try:
        supabase = get_supabase()
        
        response = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": os.getenv(
                    "OAUTH_CALLBACK_URL", 
                    "http://localhost:8000/api/auth/google/callback"
                )
            }
        })
        
        return {
            "url": response.url,
            "provider": "google",
            "message": "Redirect user to this URL"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate Google login: {str(e)}"
        )


@router.get("/callback")
async def google_callback(
    code: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None)
):
    """Handle Google OAuth callback"""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error_description or error}"
        )
    
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code"
        )
    
    try:
        supabase = get_supabase()
        
        response = supabase.auth.exchange_code_for_session({
            "auth_code": code
        })
        
        if not response or not hasattr(response, 'session') or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange code for session"
            )
        
        user_metadata = getattr(response.user, 'user_metadata', {}) or {}
        
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
            "message": "Google authentication successful"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Google callback error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


@router.get("/debug")
async def google_debug():
    """Debug endpoint for OAuth configuration"""
    try:
        supabase = get_supabase()
        
        return {
            "supabase_url": os.getenv("SUPABASE_URL"),
            "supabase_key_present": bool(os.getenv("SUPABASE_KEY")),
            "callback_url": os.getenv(
                "OAUTH_CALLBACK_URL", 
                "http://localhost:8000/api/auth/google/callback"
            ),
            "methods_available": {
                "exchange_code_for_session": hasattr(supabase.auth, 'exchange_code_for_session'),
                "sign_in_with_oauth": hasattr(supabase.auth, 'sign_in_with_oauth')
            }
        }
    except Exception as e:
        return {"error": str(e)}