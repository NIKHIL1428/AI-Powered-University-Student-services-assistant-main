"""FastAPI app. Startup: create tables, seed rules, ingest only missing/changed documents (background)."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_ask, routes_auth, routes_ingest, routes_system
from app.db.connection import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("uniassist")
BOOTSTRAP: dict = {"status": "pending"}


def _bootstrap():
    try:
        from scripts.ingest_all import ingest_all
        BOOTSTRAP["status"] = "running"
        BOOTSTRAP["documents"] = ingest_all()
        BOOTSTRAP["status"] = "done"
    except Exception as e:  # never block the API on bootstrap problems
        log.exception("bootstrap failed")
        BOOTSTRAP.update(status="error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    threading.Thread(target=_bootstrap, daemon=True).start()
    yield


app = FastAPI(title="UniAssist - NSUT Student Services Assistant", version="1.0", lifespan=lifespan)
app.include_router(routes_auth.router)
app.include_router(routes_ask.router)
app.include_router(routes_ingest.router)
app.include_router(routes_system.router)
