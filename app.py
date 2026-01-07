import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from limiter import limiter  # Import from separate file to avoid circular imports
from services.pdf_processor import GRIDDED_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER
from services.supabase_client import init_supabase
from utils.cleanup import clear_folder

load_dotenv()

# -----------------------------------------------------------------------------
# Environment setup (FIXED)
# -----------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Security for docs
security = HTTPBasic()


def verify_docs_credentials(credentials: HTTPBasicCredentials) -> bool:
    """Verify username and password for docs access"""
    correct_username = secrets.compare_digest(
        credentials.username, os.getenv("DOCS_USERNAME", "admin")
    )
    correct_password = secrets.compare_digest(
        credentials.password, os.getenv("DOCS_PASSWORD", "password")
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


# -----------------------------------------------------------------------------
# Create app
# -----------------------------------------------------------------------------
app = FastAPI(
    title="BulkForm API",
    description="Making the tedious automatic",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url="/openapi.json",
)

# -----------------------------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# -----------------------------------------------------------------------------
# CORS (THIS is what fixes browser fetch)
# -----------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "https://www.bulkform.app",
    "https://bulkform.app",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],   # includes OPTIONS preflight
    allow_headers=["*"],   # includes Authorization, Content-Type, etc.
    expose_headers=[
        "X-Forms-Needed",
        "X-Forms-Available",
        "X-Requires-Purchase",
    ],
)

# -----------------------------------------------------------------------------
# Security headers middleware (SAFE VERSION)
# IMPORTANT: DO NOT set CSP on API responses. CSP is for HTML pages.
# -----------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Security headers (always on)
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains; preload"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    path = request.url.path

    # CSP ONLY for docs + schema (pages that actually render in browser)
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )

    return response


# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Protected docs endpoints (Production only)
# -----------------------------------------------------------------------------
if IS_PRODUCTION:

    @app.get("/docs", include_in_schema=False)
    async def get_documentation(credentials: HTTPBasicCredentials = Depends(security)):
        if not verify_docs_credentials(credentials):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="BulkForm API - Documentation",
        )

    @app.get("/redoc", include_in_schema=False)
    async def get_redoc_documentation(credentials: HTTPBasicCredentials = Depends(security)):
        if not verify_docs_credentials(credentials):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return get_redoc_html(
            openapi_url="/openapi.json",
            title="BulkForm API - Documentation",
        )

# -----------------------------------------------------------------------------
# Public endpoints
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "BulkForm API", "version": "0.1.0", "environment": ENVIRONMENT}


@app.get("/health")
async def health():
    return {"status": "healthy", "api": "operational", "auth": "enabled"}


@app.get("/helloworld")
async def hello_world():
    return {"message": "Hello, World!"}
