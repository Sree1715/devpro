import os
import sys
from dotenv import load_dotenv
from db import init_db, get_user_by_email, create_user
from auth import hash_password

def main():
    # Load environment variables from .env
    load_dotenv()

    email = os.getenv("AUTHORITY_EMAIL")
    password = os.getenv("AUTHORITY_PASSWORD")
    name = os.getenv("AUTHORITY_NAME")

    # Strict check: No defaults, no hardcoded credentials
    missing = []
    if not email or not email.strip():
        missing.append("AUTHORITY_EMAIL")
    if not password or not password.strip():
        missing.append("AUTHORITY_PASSWORD")
    if not name or not name.strip():
        missing.append("AUTHORITY_NAME")

    if missing:
        print(f"ERROR: Missing required environment variable(s): {', '.join(missing)}.")
        print("Please configure them in your .env file or environment before running create_authority.py.")
        sys.exit(1)

    email = email.strip()
    password = password.strip()
    name = name.strip()

    # Ensure database schema is initialized
    try:
        init_db()
    except Exception as e:
        print(f"ERROR initializing database: {e}")
        sys.exit(1)

    # Check if authority already exists
    try:
        existing = get_user_by_email(email)
        if existing:
            if existing["role"] == "AUTHORITY":
                print(f"Authority user with email '{email}' already exists (ID: {existing['id']}).")
                sys.exit(0)
            else:
                print(f"ERROR: User with email '{email}' already exists with role '{existing['role']}'. Cannot promote to AUTHORITY.")
                sys.exit(1)

        # Hash password and create authority user
        hashed = hash_password(password)
        user_id = create_user(
            name=name,
            email=email,
            phone=None,
            password_hash=hashed,
            role="AUTHORITY"
        )
        print(f"Successfully created Authority user '{name}' ({email}) with ID: {user_id}.")
    except Exception as e:
        print(f"ERROR creating authority user: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
