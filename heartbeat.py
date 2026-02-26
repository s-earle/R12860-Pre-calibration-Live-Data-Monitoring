
import json
import time
import os

HEARTBEAT_FILE = "app_heartbeat.json"


def write_heartbeat():
    """Call once near the top of your Streamlit script (outside any tab/column)."""
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            json.dump({"ts": time.time()}, f)
    except Exception:
        pass  # never crash the UI over a heartbeat write


def cleanup_heartbeat():
    """Optionally call on a clean shutdown button to immediately signal the executor."""
    try:
        if os.path.exists(HEARTBEAT_FILE):
            os.remove(HEARTBEAT_FILE)
    except Exception:
        pass