"""Convenience launcher: `python run.py` -> http://127.0.0.1:8002"""
import os
from pathlib import Path

# Always run from the directory that contains this file so that uvicorn finds
# the correct `app/` package regardless of where Python was invoked from.
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

# Load the project environment file used by this app.
load_dotenv(ROOT / ".env.example", override=True)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        print("WARNING: GOOGLE_MAPS_API_KEY is not set — the map will not render, "
              "but ingestion / swiping / export still work.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=False)
