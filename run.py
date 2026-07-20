"""Convenience launcher: `python run.py` -> http://0.0.0.0:8002"""
import os
from pathlib import Path

# Always run from the directory that contains this file so that uvicorn finds
# the correct `app/` package regardless of where Python was invoked from.
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

# Load local/server environment variables when present.
load_dotenv(ROOT / ".env", override=False)

import uvicorn  # noqa: E402
if __name__ == "__main__":
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        print("WARNING: GOOGLE_MAPS_API_KEY is not set — the map will not render, "
              "but ingestion / swiping / export still work.")
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("APP_PORT", "8002"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
