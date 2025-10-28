"""
Supabase client configuration
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Get credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase client
supabase: Client = None

def init_supabase():
    """Initialize Supabase client"""
    global supabase
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "Missing Supabase credentials. "
            "Set SUPABASE_URL and SUPABASE_KEY environment variables."
            )
    
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

def get_supabase() -> Client:
    """Get Supabase client instance"""
    if supabase is None:
        init_supabase()
    return supabase