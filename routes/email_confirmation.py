from fastapi import APIRouter, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from services.supabase_client import get_supabase
import os
import json
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/auth/email", tags=["Email Confirmation"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8001")


@router.get("/confirm")
async def email_confirm_callback(
    request: Request,
    token_hash: str = Query(None, alias="token_hash"),
    type: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
    error_code: str = Query(None)
):
    """
    Handle email confirmation callback from Supabase
    This endpoint receives the magic link clicks from email confirmations
    """
    
    # Debug: Print what we received
    print(f"📧 Email confirm called with:")
    print(f"   token_hash: {token_hash[:20] if token_hash else None}...")
    print(f"   type: {type}")
    print(f"   error: {error}")
    print(f"   Full URL: {request.url}")
    
    # Handle errors from Supabase
    if error:
        error_msg = error_description or error
        print(f"❌ Email confirmation error: {error} - {error_description}")
        
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/?error={error}&error_description={error_msg}",
            status_code=302
        )
    
    # Validate required parameters
    if not token_hash or not type:
        print(f"❌ Missing parameters: token_hash={bool(token_hash)}, type={type}")
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/?error=invalid_request&error_description=Missing confirmation parameters",
            status_code=302
        )
    
    try:
        supabase = get_supabase()
        
        print(f"🔐 Verifying email with token_hash: {token_hash[:10]}... type: {type}")
        
        # Verify the OTP token
        response = supabase.auth.verify_otp({
            "token_hash": token_hash,
            "type": type
        })
        
        if not response or not response.session:
            print("❌ No session returned from verify_otp")
            return RedirectResponse(
                url=f"{FRONTEND_URL}/auth/?error=verification_failed&error_description=Could not verify email",
                status_code=302
            )
        
        print(f"✅ Email verified successfully for user: {response.user.email}")
        
        # Extract user info
        user_metadata = getattr(response.user, 'user_metadata', {}) or {}
        
        access_token = response.session.access_token
        refresh_token = response.session.refresh_token
        
        user = {
            "id": response.user.id,
            "email": response.user.email,
            "email_verified": True,
            "user_metadata": user_metadata
        }
        
        # Redirect to frontend with tokens (similar to Google OAuth)
        redirect_url = f"{FRONTEND_URL}/auth/callback?access_token={access_token}&refresh_token={refresh_token}&user={json.dumps(user)}&verified=true"
        print(f"✅ Redirecting to: {redirect_url}")
        
        return RedirectResponse(
            url=redirect_url,
            status_code=302
        )
        
    except Exception as e:
        import traceback
        print(f"❌ Email confirmation error: {str(e)}")
        print(traceback.format_exc())
        
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/?error=server_error&error_description={str(e)[:100]}",
            status_code=302
        )


@router.get("/debug")
async def email_debug():
    """Debug endpoint for email confirmation configuration"""
    return {
        "frontend_url": FRONTEND_URL,
        "callback_url": f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/auth/email/confirm",
        "supabase_configured": bool(os.getenv("SUPABASE_URL")),
        "supabase_url": os.getenv("SUPABASE_URL"),
    }