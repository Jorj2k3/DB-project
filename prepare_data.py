from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_PATH = DATA_DIR / "2019-Oct.csv"

TARGET_COUNT = 100_000
STREAM_LIMIT = 15_000

product_meta = {}
product_sales = {}
user_spent = {}
stream_rows = []

print(f"Streaming {RAW_PATH} in chunks...")

for chunk in pd.read_csv(RAW_PATH, chunksize=500_000):
    # 1. Collect unique product metadata (with brand & category)
    if len(product_meta) < TARGET_COUNT + 5_000:
        for row in chunk.drop_duplicates("product_id").itertuples(index=False):
            pid = int(row.product_id)
            if pid not in product_meta:
                cat = str(row.category_code).split(".")[-1] if pd.notna(row.category_code) else "general"
                brand = str(row.brand).title() if pd.notna(row.brand) else "Generic"
                product_meta[pid] = {
                    "product_id": pid,
                    "product_name": f"{brand} {cat.replace('_', ' ').title()} (#{pid})",
                    "category": cat,
                    "brand": brand,
                    "price": round(float(row.price), 2),
                }

    # 2. Collect unique users so we have >= 100k real buyers
    if len(user_spent) < TARGET_COUNT + 5_000:
        for uid in chunk["user_id"].dropna().unique():
            uid_int = int(uid)
            if uid_int not in user_spent:
                user_spent[uid_int] = 0.0

    # 3. Aggregate real purchase counts & total spend per buyer
    purchases = chunk[chunk["event_type"] == "purchase"]
    if not purchases.empty:
        for pid, cnt in purchases["product_id"].value_counts().items():
            pid_int = int(pid)
            product_sales[pid_int] = product_sales.get(pid_int, 0) + int(cnt)

        for uid, total in purchases.groupby("user_id")["price"].sum().items():
            uid_int = int(uid)
            user_spent[uid_int] = round(user_spent.get(uid_int, 0.0) + float(total), 2)

        if len(stream_rows) < STREAM_LIMIT:
            needed = STREAM_LIMIT - len(stream_rows)
            stream_rows.extend(
                purchases[["event_time", "user_id", "product_id", "price"]]
                .head(needed)
                .to_dict("records")
            )

    if (
        len(product_meta) >= TARGET_COUNT + 5_000
        and len(user_spent) >= TARGET_COUNT + 5_000
        and len(stream_rows) >= STREAM_LIMIT
    ):
        break

# Build master Products DataFrame (100,000 rows)
products_df = pd.DataFrame(list(product_meta.values())).iloc[:TARGET_COUNT].copy()
products_df["sales_count"] = products_df["product_id"].map(lambda pid: product_sales.get(pid, 0))
products_df = products_df.sample(frac=1, random_state=42).reset_index(drop=True)

# Build master Users DataFrame (100,000 rows)
users_df = pd.DataFrame(
    [{"user_id": uid, "total_spent": round(spent, 2)} for uid, spent in list(user_spent.items())[:TARGET_COUNT]]
)
users_df = users_df.sample(frac=1, random_state=42).reset_index(drop=True)

# Export 1k, 10k, and 100k slices
for size in [1000, 10000, 100000]:
    p_out = DATA_DIR / f"products_{size}.csv"
    u_out = DATA_DIR / f"users_{size}.csv"
    products_df.iloc[:size].to_csv(p_out, index=False)
    users_df.iloc[:size].to_csv(u_out, index=False)
    print(f"Saved {p_out.name} and {u_out.name} ({size:,} rows each)")

stream_out = DATA_DIR / "purchase_stream.csv"
pd.DataFrame(stream_rows).to_csv(stream_out, index=False)
print(f"Saved {stream_out.name} ({len(stream_rows):,} real purchase events)")