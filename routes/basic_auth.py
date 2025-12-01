from fastapi import APIRouter, HTTPException, status, Depends, Request
from services.supabase_client import get_supabase
from services.auth import get_current_user
from models.auth_models import (
    SignUpRequest,
    SignInRequest, 
    AuthResponse, 
    MessageResponse
)
import httpx
import os

# Import limiter from separate file (no circular import!)
from limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# hCaptcha configuration
HCAPTCHA_SECRET = os.getenv("HCAPTCHA_SECRET", "0x0000000000000000000000000000000000000000")

# Determine the correct verification URL based on secret type
if HCAPTCHA_SECRET.startswith("ES_"):
    # Enterprise secret - use enterprise endpoint
    HCAPTCHA_VERIFY_URL = "https://api.hcaptcha.com/siteverify"
    print("🏢 Using hCaptcha Enterprise endpoint")
else:
    # Standard secret - use standard endpoint  
    HCAPTCHA_VERIFY_URL = "https://hcaptcha.com/siteverify"
    print("🔒 Using hCaptcha Standard endpoint")


async def verify_captcha(token: str) -> bool:
    """Verify hCaptcha token with hCaptcha servers"""
    if not token:
        print("❌ No captcha token provided")
        return False
    
    if HCAPTCHA_SECRET == "0x0000000000000000000000000000000000000000":
        print("⚠️  Using hCaptcha test key - auto-passing validation")
        return True
    
    try:
        print(f"🔐 Verifying captcha with {HCAPTCHA_VERIFY_URL}")
        print(f"   Secret type: {'Enterprise' if HCAPTCHA_SECRET.startswith('ES_') else 'Standard'}")
        print(f"   Secret key: {HCAPTCHA_SECRET[:10]}...")
        print(f"   Token: {token[:20]}...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                HCAPTCHA_VERIFY_URL,
                data={
                    "secret": HCAPTCHA_SECRET,
                    "response": token
                },
                timeout=10.0  # Add timeout
            )
            
            result = response.json()
            print(f"✅ hCaptcha API response: {result}")
            
            success = result.get("success", False)
            if not success:
                error_codes = result.get("error-codes", [])
                print(f"❌ Captcha verification failed. Error codes: {error_codes}")
            else:
                print("✅ Captcha verification successful")
            
            return success
            
    except httpx.TimeoutException:
        print(f"❌ hCaptcha verification timeout")
        return False
    except Exception as e:
        print(f"❌ hCaptcha verification error: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        return False


@router.post("/signup")
async def signup(credentials: SignUpRequest):
    """Sign up a new user with email/password"""
    try:
        print(f"📝 Signup attempt for: {credentials.email}")
        print(f"   Options received: {credentials.options}")
        
        captcha_token = credentials.options.get("captchaToken") if credentials.options else None
        print(f"   Captcha token present: {bool(captcha_token)}")
        
        if not captcha_token:
            print("❌ No captcha token in request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Captcha verification required"
            )
        
        print("🔐 Starting captcha verification...")
        is_valid = await verify_captcha(captcha_token)
        
        if not is_valid:
            print("❌ Captcha verification failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Captcha verification failed. Please try again."
            )
        
        print("✅ Captcha verified, proceeding with signup")
        supabase = get_supabase()

        try:
            rpc_resp = supabase.rpc(
                "get_user_id_by_email",
                {"p_email": credentials.email}
            ).execute()

            existing_id = rpc_resp.data  # UUID or None
            print(f"Email pre-check existing_id={existing_id}")

            if existing_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "An account with this email already exists. "
                        "If this is you, please sign in instead."
                    )
                )
        except HTTPException:
            raise
        except Exception as check_err:
            print(f"⚠️ Email pre-check failed (continuing anyway): {check_err}")

        print("Starting Supabase signup...")
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })
        print(f"Signup response: user={bool(response.user)}, session={bool(response.session)}")

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        try:
            profile = (
                supabase
                    .table("profiles")
                    .select("*")
                    .eq("id", response.user.id)
                    .limit(1)
                    .execute()
            )
            if profile.data:
                user_data = profile.data[0]
            else:
                user_data = {
                    "id": response.user.id,
                    "email": response.user.email,
                }
        except Exception as profile_error:
            print(f"Profile fetch failed: {profile_error}")
            user_data = {
                "id": response.user.id,
                "email": response.user.email
            }
        
        if not response.session:
            print("No session - email confirmation required")
            return MessageResponse(
                message="Account created! Please check your email to confirm.",
                success=True
            )
        
        print("✅ Signup successful with session")
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user=user_data
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ SIGNUP ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Something went wrong while creating your account"
        )

@router.post("/signin", response_model=AuthResponse)
@limiter.limit("5/minute")  # Rate limit: 5 attempts per minute per IP
async def signin(request: Request, credentials: SignInRequest):
    """Sign in with email/password - rate limited to 5 attempts/minute"""
    try:
        captcha_token = credentials.options.get("captchaToken") if credentials.options else None
        
        if captcha_token:
            is_valid = await verify_captcha(captcha_token)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Captcha verification failed. Please try again."
                )
        
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


@router.get("/captcha/debug")
async def captcha_debug():
    """Debug endpoint to check captcha configuration"""
    return {
        "secret_configured": bool(HCAPTCHA_SECRET and HCAPTCHA_SECRET != "0x0000000000000000000000000000000000000000"),
        "secret_type": "Enterprise" if HCAPTCHA_SECRET.startswith("ES_") else "Standard",
        "secret_prefix": HCAPTCHA_SECRET[:10] if HCAPTCHA_SECRET else None,
        "verify_url": HCAPTCHA_VERIFY_URL,
        "note": "Visit your hCaptcha dashboard to verify your site key matches your secret"
    }
