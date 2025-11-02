"""
Test script to encrypt fill data for API testing
"""
import base64
import json
from cryptography.fernet import Fernet

# Your encryption key (get this from your .env file)
ENCRYPTION_KEY = input("Enter your GRID_ENCRYPTION_KEY: ").strip()

# Initialize cipher
cipher = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_data(data: dict) -> str:
    """Encrypt any dictionary data"""
    json_data = json.dumps(data)
    encrypted = cipher.encrypt(json_data.encode())
    return base64.b64encode(encrypted).decode()


# Your fill data
fill_data = {
    "page_number": 1,
    "text_data": [
        {
            "x": 33,
            "y": 50,
            "text": "YEKOROGHA, Ayebatariwalate",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 54,
            "y": 54,
            "text": "Friend",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 36,
            "y": 58,
            "text": "Software Engineer",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 42,
            "y": 62,
            "text": "SINGH, Pavittar",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 43,
            "y": 66,
            "text": "India",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 57,
            "y": 70,
            "text": "+2348087422585",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 55,
            "y": 74,
            "text": "tariyekorogha@gmail.com",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 46,
            "y": 78,
            "text": "123 Main Street, Lagos, Nigeria",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 24,
            "y": 89,
            "text": "A12345678",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 21,
            "y": 104,
            "text": "YEKOROGHA, Ayebatariwalate",
            "size": 30,
            "align": "center",
            "font": "arial"
        },
        {
            "x": 26,
            "y": 107,
            "text": "SINGH, Pavittar",
            "size": 30,
            "align": "center",
            "font": "arial"
        }
    ]
}

# Encrypt the data
encrypted = encrypt_data(fill_data)

print("\n" + "="*60)
print("ENCRYPTED DATA (copy this):")
print("="*60)
print(encrypted)
print("="*60)

# Get session_id
session_id = input("\nEnter your session_id: ").strip()

# Create the final payload
payload = {
    "session_id": session_id,
    "encrypted_data": encrypted
}

print("\n" + "="*60)
print("FULL PAYLOAD (copy to Swagger UI):")
print("="*60)
print(json.dumps(payload, indent=2))
print("="*60)

# Generate curl command
token = input("\nEnter your JWT token (optional, press Enter to skip): ").strip()

if token:
    curl_command = f"""
curl -X 'POST' \\
  'http://localhost:8000/api/pdf/fill-text-encrypted' \\
  -H 'accept: application/json' \\
  -H 'Authorization: Bearer {token}' \\
  -H 'Content-Type: application/json' \\
  -d '{json.dumps(payload)}'
"""
    print("\n" + "="*60)
    print("CURL COMMAND:")
    print("="*60)
    print(curl_command)
    print("="*60)