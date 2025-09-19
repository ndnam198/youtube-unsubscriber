"""
Configuration management for YouTube Subscription Manager.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- YOUTUBE API CONFIGURATION ---
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE", "client_secret.json")
SCOPES = [os.getenv("SCOPES", "https://www.googleapis.com/auth/youtube")]
API_SERVICE_NAME = os.getenv("API_SERVICE_NAME", "youtube")
API_VERSION = os.getenv("API_VERSION", "v3")
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.pickle")

# --- DATABASE CONFIGURATION ---
DB_NAME = os.getenv("DB_NAME", "youtube_subscriptions")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
