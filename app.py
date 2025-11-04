import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi import HTTPException, status
from contextlib import asynccontextmanager
from services.supabase_client import init_supabase
from routes.basic_auth import router as basic_auth_router
from routes.token_auth import router as token_auth_router
from routes.password_auth import router as password_auth_router
from routes.google_auth import router as google_auth_router
from routes.user_routes import router as user_router
from routes.pdf_routes import router as pdf_router
from routes.profile import router as profile_router
from routes.template_routes import router as template_router
from routes.batch_routes import router as batch_router
from dotenv import load_dotenv
import secrets

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (these work normally without auth)
app.include_router(basic_auth_router)
app.include_router(token_auth_router)
app.include_router(password_auth_router)
app.include_router(google_auth_router)
app.include_router(user_router)
app.include_router(profile_router)
app.include_router(pdf_router)
app.include_router(template_router)
app.include_router(batch_router)

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
            title="BulkForm API - Documentation",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
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
            title="BulkForm API - Documentation",
            redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png"
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