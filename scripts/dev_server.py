"""Run the API with the fixture profile (.env.fixtures) applied: python scripts/dev_server.py [--port 8000]"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / ".env.fixtures").read_text().splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
    uvicorn.run("app.main:app", host="127.0.0.1", port=port)
