import os
import streamlit as st
from db import init_db, get_user_by_email, create_user, get_db_path
from auth import (
    hash_password,
    verify_password,
    init_session,
    login_user,
    logout_user,
    get_current_user,
    is_authenticated,
    require_role
)
from pages_farmer import farmer_pages
from pages_authority import authority_pages

# Page configuration
st.set_page_config(
    page_title="Smart Manure",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load custom CSS
css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Initialize Session
init_session()

# Database Initialization with explicit error handling
try:
    init_db()
except Exception as db_err:
    st.error(f"Database Connection Error: Unable to access database at {get_db_path()}. Error details: {db_err}")
    st.stop()

# Authentication & Routing
current_user = get_current_user()

if not is_authenticated():
    # Public Landing Page - Only Farmer Login, Authority Login, and Farmer Register
    st.markdown('<h1 class="main-title">🌱 Smart Manure</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Smart Organic Manure Analysis and Crop Suitability Prediction System (SIH1767 – GOBARdhan)</p>',
        unsafe_allow_html=True
    )

    tab_f_login, tab_a_login, tab_f_reg = st.tabs([
        "👨‍🌾 Farmer Login",
        "🏛️ Authority Login",
        "📝 Farmer Register"
    ])

    with tab_f_login:
        st.subheader("Farmer Access Portal")
        with st.form("farmer_login_form"):
            f_email = st.text_input("Email Address", key="farmer_login_email").strip()
            f_pass = st.text_input("Password", type="password", key="farmer_login_pass")
            submitted = st.form_submit_button("Log In as Farmer", type="primary")

            if submitted:
                if not f_email or not f_pass:
                    st.error("Please enter both email and password.")
                else:
                    try:
                        user = get_user_by_email(f_email)
                        if not user:
                            st.error("No account found with this email.")
                        elif user["role"] != "FARMER":
                            st.error("Access denied: This account does not have Farmer privileges.")
                        elif not verify_password(f_pass, user["password_hash"]):
                            st.error("Incorrect password. Please try again.")
                        else:
                            login_user(user)
                            st.success(f"Welcome back, {user['name']}!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Login failed due to database error: {e}")

    with tab_a_login:
        st.subheader("Government / Authority Portal")
        st.caption("Authority accounts are provisioned via administrative setup (create_authority.py).")
        with st.form("authority_login_form"):
            a_email = st.text_input("Authority Email Address", key="auth_login_email").strip()
            a_pass = st.text_input("Password", type="password", key="auth_login_pass")
            submitted = st.form_submit_button("Log In as Authority", type="primary")

            if submitted:
                if not a_email or not a_pass:
                    st.error("Please enter both email and password.")
                else:
                    try:
                        user = get_user_by_email(a_email)
                        if not user:
                            st.error("No authority account found with this email.")
                        elif user["role"] != "AUTHORITY":
                            st.error("Access denied: This account is not registered as an Authority.")
                        elif not verify_password(a_pass, user["password_hash"]):
                            st.error("Incorrect password. Please try again.")
                        else:
                            login_user(user)
                            st.success(f"Welcome, Officer {user['name']}!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Authority login failed due to database error: {e}")

    with tab_f_reg:
        st.subheader("Register as a New Farmer")
        with st.form("farmer_register_form"):
            r_name = st.text_input("Full Name *", key="reg_name").strip()
            r_email = st.text_input("Email Address *", key="reg_email").strip()
            r_phone = st.text_input("Phone Number", key="reg_phone").strip()
            r_pass = st.text_input("Create Password *", type="password", key="reg_pass")
            r_confirm = st.text_input("Confirm Password *", type="password", key="reg_confirm")
            reg_submitted = st.form_submit_button("Create Farmer Account", type="primary")

            if reg_submitted:
                if not r_name or not r_email or not r_pass:
                    st.error("Please fill in all mandatory fields (*).")
                elif "@" not in r_email or "." not in r_email:
                    st.error("Please provide a valid email address.")
                elif len(r_pass) < 6:
                    st.error("Password must be at least 6 characters long.")
                elif r_pass != r_confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        existing = get_user_by_email(r_email)
                        if existing:
                            st.error("An account with this email address already exists. Please log in.")
                        else:
                            pwd_hash = hash_password(r_pass)
                            new_id = create_user(
                                name=r_name,
                                email=r_email,
                                phone=r_phone if r_phone else None,
                                password_hash=pwd_hash,
                                role="FARMER"
                            )
                            st.success(f"Account created successfully for {r_name}! Please switch to the Farmer Login tab to log in.")
                    except Exception as e:
                        st.error(f"Registration error: {e}")

else:
    # Logged-In Interface
    with st.sidebar:
        st.markdown(f"### 👤 Logged in as")
        st.write(f"**Name:** {current_user['name']}")
        st.write(f"**Email:** {current_user['email']}")
        st.write(f"**Role:** `{current_user['role']}`")
        st.markdown("---")
        if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
            logout_user()
            st.rerun()

    # Role enforcement and view dispatch
    if current_user["role"] == "FARMER":
        require_role(["FARMER"])
        farmer_pages(current_user)

    elif current_user["role"] == "AUTHORITY":
        require_role(["AUTHORITY"])
        authority_pages(current_user)

    else:
        st.error(f"Unauthorized or unrecognized role: {current_user.get('role')}")
        logout_user()
        st.stop()
