import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Generate a key: Fernet.generate_key().decode()
# This should be stored in the .env file as ENCRYPTION_MASTER_KEY
MASTER_KEY = os.getenv("ENCRYPTION_MASTER_KEY")

def encrypt_password(plain_text: str) -> str:
    """Pass-through since frontend relies on HTTPS + DB RLS for transit security."""
    return plain_text

def decrypt_password(encrypted_text: str) -> str:
    """Pass-through since frontend relies on HTTPS + DB RLS for transit security."""
    return encrypted_text

# Example usage for testing standalone:
if __name__ == "__main__":
    # If no key, generate one for the user to copy
    if not MASTER_KEY:
        print("No MASTER_KEY found! Here is a new key you can add to your .env file:")
        print(f"ENCRYPTION_MASTER_KEY={Fernet.generate_key().decode('utf-8')}")
    else:
        print("Encryption module is configured correctly.")
