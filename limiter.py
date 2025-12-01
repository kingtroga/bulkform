"""
Rate limiter configuration
Separate file to avoid circular imports between app.py and route files
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)