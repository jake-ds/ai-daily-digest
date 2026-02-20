#!/usr/bin/env python3
"""Run the AI Daily Digest web server."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from web.config import HOST, PORT, DEBUG


def main():
    """Run the web server."""
    print(f"Starting AI Daily Digest web server...")
    print(f"Open http://localhost:{PORT} in your browser")

    uvicorn.run(
        "web.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info",
    )


if __name__ == "__main__":
    main()
