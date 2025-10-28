from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from supabase_client import init_supabase
from routes.basic_auth import router as basic_auth_router
from routes.token_auth import router as token_auth_router
from routes.password_auth import router as password_auth_router
from routes.google_auth import router as google_auth_router
from routes.user_routes import router as user_router
from routes.profile import router as profile_router

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

app = FastAPI(
    title="BulkForm API",
    description="Automated PDF form filling with authentication",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(basic_auth_router)
app.include_router(token_auth_router)
app.include_router(password_auth_router)
app.include_router(google_auth_router)
app.include_router(user_router)
app.include_router(profile_router)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "BulkForm API",
        "version": "0.2.0",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "api": "operational",
        "auth": "enabled"
    }

@app.get("/helloworld")
async def hello_world():
    """Hello World"""
    return {
        "message": "Hello, World!"
    }