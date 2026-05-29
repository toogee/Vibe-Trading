import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Generate a key: Fernet.generate_key().decode()
# This should be stored in the .env file as ENCRYPTION_MASTER_KEY
MASTER_KEY = os.getenv("ENCRYPTION_MASTER_KEY")

def get_fernet():
    if not MASTER_KEY:
        raise ValueError("ENCRYPTION_MASTER_KEY not found in environment variables.")
    return Fernet(MASTER_KEY.encode('utf-8'))

def encrypt_password(plain_text: str) -> str:
    """Encrypts a plain text password for safe database storage."""
    fernet = get_fernet()
    encrypted_bytes = fernet.encrypt(plain_text.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')

def decrypt_password(encrypted_text: str) -> str:
    """Decrypts an encrypted password from the database."""
    fernet = get_fernet()
    decrypted_bytes = fernet.decrypt(encrypted_text.encode('utf-8'))
    return decrypted_bytes.decode('utf-8')

# Example usage for testing standalone:
if __name__ == "__main__":
    # If no key, generate one for the user to copy
    if not MASTER_KEY:
        print("No MASTER_KEY found! Here is a new key you can add to your .env file:")
        print(f"ENCRYPTION_MASTER_KEY={Fernet.generate_key().decode('utf-8')}")
    else:
        print("Encryption module is configured correctly.")
