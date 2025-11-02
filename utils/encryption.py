"""
Complete encryption for grid coordinates and fill data
Protects your API from being reverse-engineered
"""
import base64
import json
from cryptography.fernet import Fernet
import os

# Load encryption key from environment
ENCRYPTION_KEY = os.getenv("GRID_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    # Generate a key (do this once, save to .env)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"⚠️  Generated new encryption key: {ENCRYPTION_KEY}")
    print("Add this to your .env file as GRID_ENCRYPTION_KEY")

cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_data(data: dict) -> str:
    """
    Encrypt any dictionary data
    
    Args:
        data: Dictionary to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    json_data = json.dumps(data)
    encrypted = cipher.encrypt(json_data.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_data(encrypted_data: str) -> dict:
    """
    Decrypt any encrypted data
    
    Args:
        encrypted_data: Base64-encoded encrypted string
        
    Returns:
        Decrypted dictionary
    """
    try:
        encrypted_bytes = base64.b64decode(encrypted_data.encode())
        decrypted = cipher.decrypt(encrypted_bytes)
        return json.loads(decrypted.decode())
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")


# Aliases for clarity
encrypt_grid_data = encrypt_data
decrypt_grid_data = decrypt_data
encrypt_fill_data = encrypt_data
decrypt_fill_data = decrypt_data