from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.init_db import rebuild_storage


if __name__ == "__main__":
    rebuild_storage()
    print("Storage rebuilt: SQLite tables dropped/recreated and Chroma directory cleared.")
