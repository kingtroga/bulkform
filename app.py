import os
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi import HTTPException, status
from contextlib import asynccontextmanager
from services.supabase_client import init_supabase
from services.pdf_processor import TEMP_FOLDER, GRIDDED_FOLDER, OUTPUT_FOLDER
from utils.cleanup import clear_folder
from pathlib import Path
from dotenv import load_dotenv
import secrets

# Rate limiting imports
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from limiter import limiter  # Import from separate file to avoid circular imports

load_dotenv()

# Environment setup
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT

# Security for docs
security = HTTPBasic()


def verify_docs_credentials(credentials: HTTPBasicCredentials) -> bool:
    """Verify username and password for docs access"""
    correct_username = secrets.compare_digest(
        credentials.username,
        os.getenv("DOCS_USERNAME", "admin")
    )
    correct_password = secrets.compare_digest(
        credentials.password,
        os.getenv("DOCS_PASSWORD", "password")
    )
    return correct_username and correct_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events"""
    # Startup
    try:
        init_supabase()
        print("✅ Supabase connected successfully")
    except Exception as e:
        print(f"⚠️  Warning: Supabase initialization failed: {e}")

    clear_folder(TEMP_FOLDER)
    clear_folder(GRIDDED_FOLDER)
    clear_folder(OUTPUT_FOLDER)
    try:
        clear_folder("temp_pages")
    except Exception as e:
        print("Error while cleaning 'temp_pages': ", str(e))
    
    print("✅ All temporary folders cleaned up")
    
    yield
    
    # Shutdown
    print("🛑 Application shutting down...")


# Create app with NO built-in docs (we'll add custom protected ones)
app = FastAPI(
    title="BulkForm API",
    description="Making the tedious automatic",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",  # Built-in docs only in dev
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url="/openapi.json"  # Always available (needed for custom docs)
)

# Add rate limiting to app (MUST come after app creation)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.bulkform.app",
        "https://bulkform.app",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Forms-Needed",
        "X-Forms-Available",
        "X-Requires-Purchase",
    ],
)


# ============================================================================
# SECURITY HEADERS MIDDLEWARE - Added for security disclosure
# ============================================================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Security headers (always on)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    path = request.url.path

    # 🔓 Relax CSP ONLY for docs + schema
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "frame-ancestors 'none';"
            "connect-src 'self' https://www.bulkform.app https://bulkform.app;"
        )
    else:
        # 🔒 Lock down API
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )

    return response

# Import routers AFTER limiter is set up (to avoid circular imports)
from routes.basic_auth import router as basic_auth_router
from routes.token_auth import router as token_auth_router
from routes.password_auth import router as password_auth_router
from routes.google_auth import router as google_auth_router
from routes.email_confirmation import router as email_confirmation_router
from routes.user_routes import router as user_router
from routes.pdf_routes import router as pdf_router
from routes.profile import router as profile_router
from routes.template_routes import router as template_router
from routes.batch import router as batch_router
from routes.image_routes import router as image_router
from routes.payment_routes import router as payment_router
from routes.blog_routes import router as blog_router
from routes.presets_routes import router as preset_router

# Include routers
app.include_router(basic_auth_router)
app.include_router(token_auth_router)
app.include_router(password_auth_router)
app.include_router(google_auth_router)
app.include_router(email_confirmation_router)
app.include_router(user_router)
app.include_router(profile_router)
app.include_router(pdf_router)
app.include_router(template_router)
app.include_router(batch_router)
app.include_router(image_router)
app.include_router(payment_router)
app.include_router(blog_router)
app.include_router(preset_router)

# ============================================================================
# PROTECTED DOCS ENDPOINTS (Production Only)
# ============================================================================

if IS_PRODUCTION:
    @app.get("/docs", include_in_schema=False)
    async def get_documentation(credentials: HTTPBasicCredentials = Depends(security)):
        """
        Protected Swagger UI documentation
        Requires username and password in production
        """
        if not verify_docs_credentials(credentials):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="BulkForm API - Documentation"
        )


    @app.get("/redoc", include_in_schema=False)
    async def get_redoc_documentation(credentials: HTTPBasicCredentials = Depends(security)):
        """
        Protected ReDoc documentation
        Requires username and password in production
        """
        if not verify_docs_credentials(credentials):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        return get_redoc_html(
            openapi_url="/openapi.json",
            title="BulkForm API - Documentation"
        )



# ============================================================================
# PUBLIC ENDPOINTS (Always Accessible)
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - No auth required"""
    return {
        "message": "BulkForm API",
        "version": "0.1.0",
        "environment": ENVIRONMENT
    }


@app.get("/health")
async def health():
    """Health check - No auth required"""
    return {
        "status": "healthy",
        "api": "operational",
        "auth": "enabled"
    }


@app.get("/helloworld")
async def hello_world():
    """Hello World - No auth required"""
    return {
        "message": "Hello, World!"
    }