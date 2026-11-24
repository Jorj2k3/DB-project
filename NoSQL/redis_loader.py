import os
import csv
import time
from pathlib import Path
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_redis_client() -> redis.Redis:
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def get_memory_mb(r: redis.Redis) -> float:
    info = r.info("memory")
    return round(info["used_memory"] / (1024 * 1024), 2)


def load_scale(size: int, batch_size: int = 5000) -> dict:
    r = get_redis_client()
    r.flushdb()

    start = time.perf_counter()

    # 1. Load Products -> Global ZSET + Category ZSET + Metadata HASH
    p_count = 0
    categories = set()
    with open(DATA_DIR / f"products_{size}.csv", mode="r", encoding="utf-8") as f:
        pipe = r.pipeline(transaction=False)
        for row in csv.DictReader(f):
            pid = str(row["product_id"])
            score = float(row["sales_count"])
            cat = row["category"]
            categories.add(cat)

            pipe.zadd("leaderboard:products", {pid: score})
            pipe.zadd(f"leaderboard:category:{cat}", {pid: score})
            pipe.hset(
                f"product:{pid}",
                mapping={
                    "name": row["product_name"],
                    "category": cat,
                    "brand": row["brand"],
                    "price": row["price"],
                },
            )

            p_count += 1
            if p_count % batch_size == 0:
                pipe.execute()
        pipe.execute()

    # 2. Load Buyers -> Buyers ZSET
    u_count = 0
    with open(DATA_DIR / f"users_{size}.csv", mode="r", encoding="utf-8") as f:
        pipe = r.pipeline(transaction=False)
        for row in csv.DictReader(f):
            uid = str(row["user_id"])
            spent = float(row["total_spent"])
            pipe.zadd("leaderboard:buyers", {uid: spent})

            u_count += 1
            if u_count % batch_size == 0:
                pipe.execute()
        pipe.execute()

    elapsed = round(time.perf_counter() - start, 3)
    mem_mb = get_memory_mb(r)
    print(
        f"[Redis] Loaded {p_count:,} products ({len(categories)} categories) & "
        f"{u_count:,} buyers in {elapsed}s | RAM: {mem_mb} MB"
    )
    return {"size": size, "load_sec": elapsed, "memory_mb": mem_mb, "categories": len(categories)}


if __name__ == "__main__":
    load_scale(1000)