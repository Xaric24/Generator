"""Scryfall data provider with Mongo caching, throttling and retries."""
import asyncio
import time
import logging
import requests

logger = logging.getLogger("scryfall")
BASE = "https://api.scryfall.com"
CACHE_TTL = 7 * 24 * 3600
_last_call = [0.0]
_lock = asyncio.Lock()


def _now():
    return time.time()


class Scryfall:
    def __init__(self, db):
        self.db = db
        self.cache = db.scryfall_cache

    async def _throttle(self):
        async with _lock:
            delta = _now() - _last_call[0]
            if delta < 0.11:
                await asyncio.sleep(0.11 - delta)
            _last_call[0] = _now()

    def _req(self, method, path, params=None, json=None):
        url = path if path.startswith("http") else f"{BASE}{path}"
        for attempt in range(4):
            try:
                r = requests.request(method, url, params=params, json=json,
                                     headers={"User-Agent": "CommanderForgeAI/1.0",
                                              "Accept": "application/json"}, timeout=20)
                if r.status_code == 429:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except Exception as e:
                logger.warning("scryfall %s attempt %s failed: %s", path, attempt, e)
                time.sleep(0.4 * (2 ** attempt))
        return None

    async def _cached(self, key, method, path, params=None, json=None):
        doc = await self.cache.find_one({"_id": key})
        if doc and _now() - doc.get("t", 0) < CACHE_TTL:
            return doc["d"]
        await self._throttle()
        data = await asyncio.to_thread(self._req, method, path, params, json)
        if data is not None:
            await self.cache.update_one({"_id": key}, {"$set": {"d": data, "t": _now()}}, upsert=True)
            return data
        if doc:  # offline fallback to stale
            return doc["d"]
        return None

    async def autocomplete(self, q):
        d = await self._cached(f"ac:{q.lower()}", "GET", "/cards/autocomplete", {"q": q})
        return (d or {}).get("data", [])

    async def named(self, name):
        return await self._cached(f"named:{name.lower()}", "GET", "/cards/named", {"exact": name})

    async def fuzzy(self, name):
        return await self._cached(f"fuzzy:{name.lower()}", "GET", "/cards/named", {"fuzzy": name})

    async def search(self, query, limit=60, order="edhrec"):
        key = f"srch:{order}:{query.lower()}:{limit}"
        doc = await self.cache.find_one({"_id": key})
        if doc and _now() - doc.get("t", 0) < CACHE_TTL:
            return doc["d"]
        await self._throttle()
        first = await asyncio.to_thread(self._req, "GET", "/cards/search",
                                        {"q": query, "order": order, "unique": "cards"})
        cards = []
        if first and first.get("data"):
            cards.extend(first["data"])
        # single extra page is enough for our limits
        if first and first.get("has_more") and len(cards) < limit:
            await self._throttle()
            nxt = await asyncio.to_thread(self._req, "GET", first["next_page"])
            if nxt and nxt.get("data"):
                cards.extend(nxt["data"])
        cards = cards[:limit]
        await self.cache.update_one({"_id": key}, {"$set": {"d": cards, "t": _now()}}, upsert=True)
        return cards

    async def collection(self, names):
        """Resolve up to 75 names at a time via /cards/collection."""
        out = []
        for i in range(0, len(names), 75):
            chunk = names[i:i + 75]
            ids = [{"name": n} for n in chunk]
            data = await self._cached("coll:" + "|".join(sorted(chunk)).lower(),
                                      "POST", "/cards/collection", json={"identifiers": ids})
            if data and data.get("data"):
                out.extend(data["data"])
        return out
