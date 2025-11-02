"""
Encryption utilities for protecting grid coordinates
"""
import base64
import json
from cryptography.fernet import Fernet
import os

# Load or generate encryption key
ENCRYPTION_KEY = os.getenv("GRID_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Generate a key (do this once, save to .env)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"⚠️  Generated new encryption key: {ENCRYPTION_KEY}")
    print("Add this to your .env file as GRID_ENCRYPTION_KEY")

cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_grid_data(data: dict) -> str:
    """
    Encrypt grid coordinate data
    
    Args:
        data: Dictionary to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    json_data = json.dumps(data)
    encrypted = cipher.encrypt(json_data.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_grid_data(encrypted_data: str) -> dict:
    """
    Decrypt grid coordinate data
    
    Args:
        encrypted_data: Base64-encoded encrypted string
        
    Returns:
        Decrypted dictionary
    """
    encrypted_bytes = base64.b64decode(encrypted_data.encode())
    decrypted = cipher.decrypt(encrypted_bytes)
    return json.loads(decrypted.decode())