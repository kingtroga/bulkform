from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from services.supabase_client import get_supabase
import os
import json
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/auth/google", tags=["OAuth - Google"])

FRONTEND_URL=os.getenv("FRONTEND_URL", "http://localhost:8001")

@router.get("")
async def google_login():
    """Initiate Google OAuth login"""
    try:
        supabase = get_supabase()
        
        response = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": "https://bulkform-51hd.onrender.com/api/auth/google/callback"
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
        app_metadata = getattr(response.user, 'app_metadata', {}) or {}

        access_token = response.session.access_token
        refresh_token = response.session.refresh_token
        
        # Build identities array for auth provider detection
        identities = []
        if hasattr(response.user, 'identities') and response.user.identities:
            identities = [
                {
                    "provider": identity.provider,
                    "id": getattr(identity, 'id', None)
                }
                for identity in response.user.identities
            ]
        
        user = {
            "id": response.user.id,
            "email": response.user.email,
            "name": user_metadata.get("full_name") or user_metadata.get("name", ""),
            "avatar": user_metadata.get("avatar_url") or user_metadata.get("picture", ""),
            "email_verified": getattr(response.user, 'email_confirmed_at', None) is not None,
            # Add identity info for password status detection
            "identities": identities,
            "app_metadata": app_metadata,
            "user_metadata": user_metadata
        }

        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}&user={json.dumps(user)}"
        )
        
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