"""
welfog_sync.py  —  Welfog DBs → AI Personalization Engine
===========================================================
YEH FILE YAHAN RAKHO:
  ai-personalization-engine-phase5/backend/welfog_sync.py

INSTALL:
  pip install asyncpg aiomysql httpx python-dotenv

RUN:
  cd backend
  python welfog_sync.py
"""

import asyncio
import hashlib
import os
from datetime import datetime, timezone

import asyncpg
import aiomysql
import httpx
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG (Purely loaded from .env - No hardcoded secrets) ─────────
# PostgreSQL Configuration (.env: POSTGRES_*)
PG = dict(
    host     = os.getenv("POSTGRES_HOST", "localhost"),
    port     = int(os.getenv("POSTGRES_PORT", 5433)),
    database = os.getenv("POSTGRES_DB", "welfog_product"),
    user     = os.getenv("POSTGRES_USER", ""),
    password = (os.getenv("POSTGRES_PASSWORD", "")).strip(),
)

# MySQL Configuration (.env: DB_*)
MY = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 3306)),
    db       = os.getenv("DB_NAME", "welfog_db"),
    user     = os.getenv("DB_USER", ""),
    password = (os.getenv("DB_PASSWORD", "")).strip(),
    charset  = "utf8mb4",
    autocommit = True,
)

# AI Engine API Configuration (.env: AI_ENGINE_*)
AI_URL      = (os.getenv("AI_ENGINE_URL") or os.getenv("AI_BASE_URL", "http://localhost:8000/api/v1")).rstrip("/")
AI_EMAIL    = os.getenv("AI_ENGINE_EMAIL", "")
AI_PASSWORD = os.getenv("AI_ENGINE_PASSWORD", "")
_raw_token  = os.getenv("AI_SERVICE_TOKEN", "")
AI_TOKEN    = _raw_token.removeprefix("AI_SERVICE_TOKEN=").strip() if _raw_token else ""
BATCH       = 200

# ─── HELPERS ──────────────────────────────────────────────
def _ikey(*parts) -> str:
    return hashlib.md5("_".join(str(p) for p in parts).encode()).hexdigest()

def _dt(val) -> str:
    if val is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.isoformat()
    return str(val)

async def _ensure_token(http: httpx.AsyncClient) -> str:
    global AI_TOKEN
    if AI_TOKEN:
        return AI_TOKEN
    try:
        r = await http.post(f"{AI_URL}/auth/login", json={"email": AI_EMAIL, "password": AI_PASSWORD}, timeout=10)
        if r.status_code == 200:
            AI_TOKEN = r.json().get("data", {}).get("access_token", "")
            print("   🔑 AI Engine token acquired automatically!")
            return AI_TOKEN
    except Exception as exc:  # noqa: BLE001
        print(f"   ⚠ Auto-login attempt failed: {exc}")
    return ""

async def _post(http, path, body, label) -> bool:
    global AI_TOKEN
    for attempt in range(2):
        if not AI_TOKEN and path.startswith("/products"):
            await _ensure_token(http)
        headers = {}
        if AI_TOKEN:
            headers["Authorization"] = f"Bearer {AI_TOKEN}"
        storefront_key = os.getenv("STOREFRONT_API_KEY")
        if storefront_key:
            headers["X-API-Key"] = storefront_key
        try:
            r = await http.post(f"{AI_URL}{path}", json=body, headers=headers, timeout=60)
            if r.status_code in (200, 201):
                return True
            if r.status_code == 401 and attempt == 0:
                AI_TOKEN = ""
                await _ensure_token(http)
                continue
            print(f"  ⚠ {label} → HTTP {r.status_code}: {r.text[:120]}")
            return False
        except Exception as e:
            print(f"  ✗ {label} → {e}")
            return False
    return False

async def _send_events(http, events, label):
    if not events:
        print(f"  ✓ {label}: 0 events (skip)")
        return
    ok = fail = 0
    for i in range(0, len(events), BATCH):
        chunk = events[i:i+BATCH]
        if await _post(http, "/events/batch", {"events": chunk}, f"{label} batch {i//BATCH+1}"):
            ok += len(chunk)
        else:
            fail += len(chunk)
    print(f"  ✓ {label}: {ok} gaye, {fail} fail")


# ─── 1. PRODUCTS ──────────────────────────────────────────
async def sync_products(pg, http):
    print("\n📦 Products sync ho raha hai...")
    rows = await pg.fetch("""
        SELECT
            pro_id        AS product_id,
            name,
            category_name AS category,
            brand,
            tags,
            purchase_price,
            stock,
            rating,
            thumb_url
        FROM public.products
        WHERE published = 1
          AND approved  = 1
          AND hold      = 0
          AND block     = 0
          AND name      IS NOT NULL
          AND pro_id    IS NOT NULL
        ORDER BY pro_id
    """)
    print(f"  → {len(rows)} active products mile")

    items = []
    for r in rows:
        tags = [t.strip() for t in (r["tags"] or "").split(",") if t.strip()]
        try:
            price = float(r["purchase_price"] or 0)
        except Exception:
            price = 0.0
        items.append({
            "product_id": str(r["product_id"]),
            "name":       (r["name"] or "").strip(),
            "category":   r["category"] or "Uncategorized",
            "brand":      r["brand"] or "",
            "price":      price,
            "rating":     float(r["rating"] or 0),
            "tags":       tags,
            "in_stock":   bool((r["stock"] or 0) > 0),
            "is_active":  True,
            "image_url":  f"https://cdn.welfog.com/{r['thumb_url']}" if r["thumb_url"] else "",
        })

    ok = fail = 0
    for i in range(0, len(items), BATCH):
        chunk = items[i:i+BATCH]
        if await _post(http, "/products/bulk", {"products": chunk}, f"Products batch {i//BATCH+1}"):
            ok += len(chunk)
        else:
            fail += len(chunk)
    print(f"  ✓ Products: {ok} sync hue, {fail} fail")


# ─── 2. ORDERS ────────────────────────────────────────────
# Welfog mein order_details KHALI hai
# Sab data ORDERS table mein directly hai:
# orders.product_id, orders.user_id, orders.quantity, orders.grand_total
async def sync_orders(my, http):
    print("\n🛒 Order events sync ho rahe hain...")
    async with my.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("""
            SELECT
                id           AS order_id,
                user_id,
                product_id,
                quantity,
                grand_total  AS price,
                created_at
            FROM orders
            WHERE user_id    IS NOT NULL
              AND product_id IS NOT NULL
              AND quantity   > 0
            ORDER BY created_at DESC
            LIMIT 10000
        """)
        rows = await cur.fetchall()

    print(f"  → {len(rows)} orders mile")

    events = []
    for r in rows:
        if not r["user_id"] or not r["product_id"]:
            continue
        events.append({
            "event_type":       "PURCHASE",
            "external_user_id": str(r["user_id"]),
            "product_id":       str(r["product_id"]),
            "session_id":       f"order_{r['order_id']}",
            "platform":         "web",
            "timestamp":        _dt(r["created_at"]),
            "idempotency_key":  _ikey("purchase", r["order_id"], r["product_id"]),
            "metadata": {
                "amount":   float(r["price"] or 0),
                "quantity": int(r["quantity"] or 1),
                "order_id": str(r["order_id"]),
            },
        })

    await _send_events(http, events, "Purchase events")


# ─── 3. WISHLISTS ─────────────────────────────────────────
async def sync_wishlists(my, http):
    print("\n💖 Wishlist events sync ho rahe hain...")
    async with my.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("""
            SELECT user_id, product_id, created_at
            FROM wishlists
            WHERE user_id IS NOT NULL AND product_id IS NOT NULL
            ORDER BY created_at DESC LIMIT 5000
        """)
        rows = await cur.fetchall()
    print(f"  → {len(rows)} wishlist entries mile")

    events = [
        {
            "event_type":       "WISHLIST_ADD",
            "external_user_id": str(r["user_id"]),
            "product_id":       str(r["product_id"]),
            "session_id":       f"wish_{r['user_id']}",
            "platform":         "web",
            "timestamp":        _dt(r["created_at"]),
            "idempotency_key":  _ikey("wish", r["user_id"], r["product_id"]),
            "metadata":         {},
        }
        for r in rows if r["user_id"] and r["product_id"]
    ]
    await _send_events(http, events, "Wishlist events")


# ─── 4. REVIEWS ───────────────────────────────────────────
async def sync_reviews(my, http):
    print("\n⭐ Review events sync ho rahe hain...")
    async with my.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("""
            SELECT user_id, product_id, rating, created_at
            FROM reviews
            WHERE status = 1
              AND user_id IS NOT NULL AND product_id IS NOT NULL
        """)
        rows = await cur.fetchall()
    print(f"  → {len(rows)} reviews mile")

    events = [
        {
            "event_type":       "PRODUCT_REVIEW",
            "external_user_id": str(r["user_id"]),
            "product_id":       str(r["product_id"]),
            "session_id":       f"review_{r['user_id']}",
            "platform":         "web",
            "timestamp":        _dt(r["created_at"]),
            "idempotency_key":  _ikey("review", r["user_id"], r["product_id"]),
            "metadata":         {"rating": int(r["rating"] or 0)},
        }
        for r in rows if r["user_id"] and r["product_id"]
    ]
    await _send_events(http, events, "Review events")


# ─── MAIN ─────────────────────────────────────────────────
async def main():
    print("=" * 55, flush=True)
    print("🚀  Welfog → AI Personalization Sync", flush=True)
    print(f"    AI URL : {AI_URL}", flush=True)
    print(f"    Samay  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 55, flush=True)

    print("\n🔌 PostgreSQL se connect ho raha hai...", flush=True)
    if not PG["user"] or not PG["password"]:
        print("   ❌ PostgreSQL fail: POSTGRES_USER or POSTGRES_PASSWORD missing in .env!", flush=True)
        return
    try:
        pg = await asyncpg.connect(**PG, timeout=10)
        print("   ✅ PostgreSQL connected!", flush=True)
    except Exception as e:
        print(f"   ❌ PostgreSQL fail: {e}", flush=True)
        return

    print("🔌 MySQL se connect ho raha hai...", flush=True)
    if not MY["user"]:
        print("   ❌ MySQL fail: DB_USER missing in .env!", flush=True)
        await pg.close()
        return
    try:
        my = await aiomysql.connect(**MY, connect_timeout=10)
        print("   ✅ MySQL connected!", flush=True)
    except Exception as e:
        print(f"   ❌ MySQL fail: {e}", flush=True)
        await pg.close()
        return

    print(f"🔌 AI backend check ho raha hai ({AI_URL})...", flush=True)
    async with httpx.AsyncClient() as http:
        try:
            r = await http.get(f"{AI_URL}/health", timeout=5)
            print("   ✅ AI backend chal raha hai!", flush=True)
        except Exception:
            print(f"   ❌ AI backend nahi mila! Make sure backend is running on {AI_URL}", flush=True)
            await pg.close()
            my.close()
            return

        await sync_products(pg, http)
        await sync_orders(my, http)
        await sync_wishlists(my, http)
        await sync_reviews(my, http)

    await pg.close()
    my.close()

    print("\n" + "=" * 55)
    print("✅  Sync poora hua!")
    print("   Dashboard → Customers → Recompute dabao")
    print("   Segments ban jayenge real data se!")
    print("=" * 55)

if __name__ == "__main__":
    asyncio.run(main())

