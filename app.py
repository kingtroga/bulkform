from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="BulkForm API",
    description="API for automated PDF form filling",
    version="0.1.0"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "BulkForm API is running",
        "version": "0.1.0"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "api": "operational"
    }
@app.get("/helloworld")
async def hello_world():
    """Hello world endpoint"""
    return {
        "message": "Hello from BulkForm! 🚀🧑‍🚀",
        "description": "Automated PDF form filling API"
    }