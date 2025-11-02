"""
Encrypt batch fill data for multiple pages
"""
import base64
import json
from cryptography.fernet import Fernet

# Your encryption key
ENCRYPTION_KEY = input("Enter your GRID_ENCRYPTION_KEY: ").strip()
cipher = Fernet(ENCRYPTION_KEY.encode())

# Batch fill data (multiple pages)
batch_data = {
    "pages": [
        {
            "page_number": 1,
            "text_data": [
                {
                    "x": 33,
                    "y": 50,
                    "text": "YEKOROGHA, Ayebatariwalate",
                    "size": 30,
                    "align": "center",
                    "font": "Danfo"
                },
                {
                    "x": 54,
                    "y": 54,
                    "text": "Friend",
                    "size": 30,
                    "align": "center",
                    "font": "Danfo"
                }
            ]
        },
        {
            "page_number": 2,
            "text_data": [
                {
                    "x": 20,
                    "y": 30,
                    "text": "Page 2 Content",
                    "size": 25,
                    "align": "top",
                    "font": "Danfo"
                }
            ]
        }
    ]
}

# Encrypt
encrypted = base64.b64encode(cipher.encrypt(json.dumps(batch_data).encode())).decode()

print("\n" + "="*60)
print("ENCRYPTED BATCH DATA:")
print("="*60)
print(encrypted)
print("="*60)

session_id = input("\nEnter your session_id: ").strip()

payload = {
    "session_id": session_id,
    "encrypted_data": encrypted
}

print("\n" + "="*60)
print("FULL PAYLOAD:")
print("="*60)
print(json.dumps(payload, indent=2))
print("="*60)
