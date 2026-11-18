import bcrypt
import streamlit as st
from typing import Optional, Dict, Any

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def init_session():
    """Ensure session state variables for authentication exist."""
    if "user" not in st.session_state:
        st.session_state["user"] = None
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

def login_user(user: Dict[str, Any]):
    """Set current user session."""
    st.session_state["user"] = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"]
    }
    st.session_state["authenticated"] = True

def logout_user():
    """Clear session state on logout."""
    st.session_state["user"] = None
    st.session_state["authenticated"] = False

def get_current_user() -> Optional[Dict[str, Any]]:
    """Get currently logged-in user dict from session."""
    return st.session_state.get("user")

def is_authenticated() -> bool:
    """Return whether a user is currently authenticated."""
    return bool(st.session_state.get("authenticated") and st.session_state.get("user"))

def require_role(allowed_roles: list) -> bool:
    """Enforce role checking for the current page. If unauthorized, stop execution."""
    user = get_current_user()
    if not user:
        st.error("Authentication required. Please log in.")
        st.stop()
        return False
    if user.get("role") not in allowed_roles:
        st.error(f"Unauthorized: Access restricted to {', '.join(allowed_roles)}.")
        st.stop()
        return False
    return True
