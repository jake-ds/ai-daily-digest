"""Web application configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"

# Database
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Server
HOST = os.getenv("WEB_HOST", "0.0.0.0")
PORT = int(os.getenv("WEB_PORT", "8000"))
DEBUG = os.getenv("WEB_DEBUG", "true").lower() == "true"

# API Keys (inherited from main app)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_ARTICLES_DATABASE_ID = os.getenv("NOTION_ARTICLES_DATABASE_ID")

# Collection settings
DEFAULT_COLLECTION_HOURS = 48
DEFAULT_HN_LIMIT = 30
DEFAULT_ARTICLE_LIMIT = 50

# LinkedIn settings
LINKEDIN_GUIDELINES_PATH = DATA_DIR / "linkedin_guidelines.md"
