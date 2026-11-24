from decimal import Decimal

def format_product_id(product_id):
    return f"{int(product_id):012d}"

def record_purchase(r, user_id, product_id, price, event_time):
    pid = format_product_id(product_id)
    uid = str(user_id)
    price_float = float(price)

    category = r.hget(f"product:{pid}", "category")

    pipe = r.pipeline(transaction=True)
    pipe.zincrby("leaderboard:products", 1, pid)
    if category:
        pipe.zincrby(f"leaderboard:category:{category}", 1, pid)
    pipe.zincrby("leaderboard:buyers", price_float, uid)
    pipe.xadd(
        "stream:purchases",
        {
            "user_id": uid,
            "product_id": pid,
            "price": str(price),
            "event_time": str(event_time),
        },
        maxlen=1000,
        approximate=True,
    )
    pipe.execute()


def increment_score(r, product_id):
    r.zincrby(
        "leaderboard:products",
        1,
        format_product_id(product_id)
    )


def get_top_k(r, k=10):

    top_items = r.zrange(
        "leaderboard:products", 0, k - 1, desc=True, withscores=True
    )
    if not top_items:
        return []

    pipe = r.pipeline(transaction=False)
    for pid, _ in top_items:
        pipe.hget(f"product:{pid}", "name")
    names = pipe.execute()

    return [
        (int(pid), name or f"Product #{pid}", int(score))
        for (pid, score), name in zip(top_items, names)
    ]


def get_rank(r, product_id):
    rank = r.zrevrank(
        "leaderboard:products",
        format_product_id(product_id)
    )

    return (rank + 1) if rank is not None else None


def get_product(r, product_id):

    pid = format_product_id(product_id)
    pipe = r.pipeline(transaction=False)
    pipe.hgetall(f"product:{pid}")
    pipe.zscore("leaderboard:products", pid)
    meta, score = pipe.execute()

    if not meta or score is None:
        return None

    return (
        int(product_id),
        meta.get("name", f"Product #{pid}"),
        meta.get("category", "unknown"),
        meta.get("brand", "Unknown"),
        Decimal(str(meta.get("price", "0.00"))),
        int(score),
    )