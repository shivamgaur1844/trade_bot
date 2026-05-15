import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Angel One SmartAPI Credentials
# Get these from https://smartapi.angelbroking.com/
API_KEY = os.getenv("ANGEL_API_KEY", "YOUR_API_KEY_HERE")
CLIENT_ID = os.getenv("ANGEL_CLIENT_CODE", os.getenv("ANGEL_CLIENT_ID", "YOUR_CLIENT_ID_HERE"))
PASSWORD = os.getenv("ANGEL_PASSWORD", "YOUR_PIN_HERE")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "YOUR_TOTP_SECRET_HERE")

# General Settings
DEBUG_MODE = True
