from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
client = AsyncIOMotorClient(mongo_url) if mongo_url and db_name else None
db = client[db_name] if client is not None else None

try:
    from .scryfall import Scryfall
    from . import engine, llm_service
except ImportError:  # Local `cd backend && uvicorn server:app` support.
    from scryfall import Scryfall
    import engine
    import llm_service

sf = Scryfall(db) if db is not None else None

app = FastAPI(title="Commander Forge AI")
api = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")


class GenParams(BaseModel):
    commander: str
    mode: str = "optimized"
    theme: Optional[str] = None
    budget: Optional[float] = None
    max_price_per_card: Optional[float] = None
    land_count: int = 32
    locks: List[str] = Field(default_factory=list)
    excludes: List[str] = Field(default_factory=list)
    local_bans: List[str] = Field(default_factory=list)
    owned: List[str] = Field(default_factory=list)
    toggles: Dict[str, bool] = Field(default_factory=dict)
    seed: Optional[int] = None


class ImproveParams(BaseModel):
    decklist: str
    commander: Optional[str] = None


def _clean(p: GenParams):
    return {
        "commander": p.commander, "mode": p.mode, "theme": p.theme, "budget": p.budget,
        "max_price_per_card": p.max_price_per_card, "land_count": p.land_count,
        "locks": p.locks, "excludes": set(p.excludes), "local_bans": set(p.local_bans),
        "owned": set(p.owned), "toggles": p.toggles or {}, "seed": p.seed,
    }


def _require_backend():
    if sf is None or db is None:
        raise HTTPException(
            503,
            "Backend storage is not configured. Set MONGO_URL and DB_NAME in the API host environment.",
        )
    return sf, db


@api.get("/")
async def root():
    return {
        "app": "Commander Forge AI",
        "ai_available": llm_service.available(),
        "database_configured": db is not None,
    }


@api.get("/commanders/search")
async def search_commanders(q: str):
    provider, _ = _require_backend()
    if len(q) < 2:
        return {"results": []}
    names = await provider.autocomplete(q)
    out = []
    for n in names[:12]:
        out.append(n)
    return {"results": out}


@api.get("/card")
async def get_card(name: str):
    provider, _ = _require_backend()
    raw = await provider.named(name) or await provider.fuzzy(name)
    if not raw:
        raise HTTPException(404, "Card not found")
    return engine.norm_card(raw)


import asyncio

JOBS = {}


def _serverless_sync_generate():
    return os.environ.get("SERVERLESS_SYNC_GENERATE") == "1" or os.environ.get("VERCEL") == "1"


async def _save_deck(database, params, result):
    doc = {"_id": str(uuid.uuid4()), "created": datetime.now(timezone.utc).isoformat(),
           "commander": params["commander"], "mode": params["mode"], "result": result}
    await database.decks.insert_one(doc)
    result["deck_id"] = doc["_id"]
    return result


async def _run_generate(job_id, params):
    def prog(msg):
        if job_id in JOBS:
            JOBS[job_id]["progress"] = msg
    try:
        provider, database = _require_backend()
        result = await engine.generate(provider, database, params, progress=prog)
        if result.get("error"):
            JOBS[job_id] = {"status": "error", "error": result["error"], "progress": ""}
            return
        result = await _save_deck(database, params, result)
        JOBS[job_id] = {"status": "done", "result": result, "progress": "Complete"}
    except Exception as e:
        logger.exception("job failed")
        JOBS[job_id] = {"status": "error", "error": str(e), "progress": ""}


@api.post("/generate")
async def generate(p: GenParams):
    provider, database = _require_backend()
    job_id = str(uuid.uuid4())
    params = _clean(p)
    if _serverless_sync_generate():
        try:
            result = await engine.generate(provider, database, params, progress=lambda _msg: None)
            if result.get("error"):
                return {"job_id": job_id, "status": "error", "error": result["error"]}
            result = await _save_deck(database, params, result)
            return {"job_id": job_id, "status": "done", "result": result}
        except Exception as e:
            logger.exception("serverless generation failed")
            return {"job_id": job_id, "status": "error", "error": str(e)}
    JOBS[job_id] = {"status": "running", "progress": "Queued...", "result": None}
    asyncio.create_task(_run_generate(job_id, params))
    return {"job_id": job_id}


@api.get("/generate/status/{job_id}")
async def generate_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"status": job["status"], "progress": job.get("progress", ""),
            "result": job.get("result"), "error": job.get("error")}


@api.post("/improve")
async def improve(p: ImproveParams):
    provider, database = _require_backend()
    try:
        result = await engine.improve_deck(provider, database, {"decklist": p.decklist, "commander": p.commander})
    except Exception as e:
        logger.exception("improve failed")
        raise HTTPException(500, f"Analysis failed: {e}")
    return result


@api.get("/decks")
async def list_decks():
    _, database = _require_backend()
    docs = await database.decks.find({}, {"result": 0}).sort("created", -1).to_list(30)
    return {"decks": docs}


@api.get("/decks/{deck_id}")
async def get_deck(deck_id: str):
    _, database = _require_backend()
    doc = await database.decks.find_one({"_id": deck_id})
    if not doc:
        raise HTTPException(404, "Deck not found")
    return doc["result"]


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True,
                   allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("shutdown")
async def shutdown():
    if client is not None:
        client.close()
