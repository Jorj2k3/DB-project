
from pathlib import Path
from collections import Counter

import pandas as pd
import numpy as np

# Configuration

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_PATH = DATA_DIR / "2019-Oct.csv"

CHUNK_SIZE = 500_000
TARGET_COUNT = 100_000
STREAM_LIMIT = 15_000

DATASET_SIZES = [1000, 10000, 100000]
RANDOM_SEED = 42

rng = np.random.default_rng(RANDOM_SEED)

# Storage for extracted and aggregated data

product_meta = {}
product_sales = Counter()
user_spent = Counter()
unique_users = set()

print("Processing raw dataset...")

# 1. Process the entire dataset in chunks

for i, chunk in enumerate(
    pd.read_csv(
        RAW_PATH,
        chunksize=CHUNK_SIZE,
        usecols=[
            "event_type",
            "product_id",
            "category_code",
            "brand",
            "price",
            "user_id"
        ]
    ),
    start=1
):

    # Extract product metadata

    unique_products = chunk.drop_duplicates("product_id")

    for row in unique_products.itertuples(index=False):

        if pd.isna(row.product_id):
            continue

        pid = int(row.product_id)

        if pid not in product_meta:

            category = (
                str(row.category_code)
                if pd.notna(row.category_code)
                else "unknown"
            )

            brand = (
                str(row.brand).title()
                if pd.notna(row.brand)
                else "Unknown"
            )

            if pd.isna(row.price) or row.price < 0:
                continue

            product_meta[pid] = {
                "product_id": pid,
                "product_name": (
                    f"{brand} "
                    f"{category.split('.')[-1].title()} "
                    f"(#{pid})"
                ),
                "category": category,
                "brand": brand,
                "price": round(float(row.price), 2)
            }

    # Extract unique users

    unique_users.update(
        int(uid)
        for uid in chunk["user_id"].dropna().unique()
    )

    # Filter valid purchase events

    purchases = chunk[
        (chunk["event_type"] == "purchase")
        & chunk["product_id"].notna()
        & chunk["user_id"].notna()
        & chunk["price"].notna()
        & (chunk["price"] >= 0)
    ]

    # Aggregate purchase counts

    product_sales.update(
        purchases["product_id"].value_counts().to_dict()
    )

    # Aggregate customer spending

    spending = purchases.groupby("user_id")["price"].sum()

    user_spent.update(spending.to_dict())

    print(f"Chunk {i} processed")

# 2. Build the master products dataset

products_df = pd.DataFrame(product_meta.values())

products_df["sales_count"] = (
    products_df["product_id"]
    .map(product_sales)
    .fillna(0)
    .astype("int64")
)

if len(products_df) < TARGET_COUNT:
    raise ValueError("Not enough unique products")

products_df = products_df.sample(
    n=TARGET_COUNT,
    random_state=RANDOM_SEED
).reset_index(drop=True)

# 3. Build the master users dataset

if len(unique_users) < TARGET_COUNT:
    raise ValueError("Not enough unique users")

selected_users = rng.choice(
    sorted(unique_users),
    size=TARGET_COUNT,
    replace=False
)

users_df = pd.DataFrame({
    "user_id": selected_users
})

users_df["total_spent"] = (
    users_df["user_id"]
    .map(user_spent)
    .fillna(0)
    .round(2)
)

# 4. Generate experimental datasets

for size in DATASET_SIZES:

    products = products_df.iloc[:size].copy()
    users = users_df.iloc[:size].copy()

    products.to_csv(
        DATA_DIR / f"products_{size}.csv",
        index=False
    )

    users.to_csv(
        DATA_DIR / f"users_{size}.csv",
        index=False
    )

    # 5. Generate synthetic purchase events

    # Popular products have a higher purchase probability.
    # Adding 1 also allows products with zero sales
    # to receive new purchases.

    weights = (
        products["sales_count"].to_numpy(dtype=float) + 1
    )

    probabilities = weights / weights.sum()

    selected_products = rng.choice(
        products["product_id"].to_numpy(),
        size=STREAM_LIMIT,
        replace=True,
        p=probabilities
    )

    selected_buyers = rng.choice(
        users["user_id"].to_numpy(),
        size=STREAM_LIMIT,
        replace=True
    )

    price_map = products.set_index("product_id")["price"]

    purchase_stream = pd.DataFrame({
        "event_time": pd.date_range(
            start="2019-11-01",
            periods=STREAM_LIMIT,
            freq="s",
            tz="UTC"
        ),
        "user_id": selected_buyers,
        "product_id": selected_products
    })

    purchase_stream["price"] = (
        purchase_stream["product_id"].map(price_map)
    )

    purchase_stream.to_csv(
        DATA_DIR / f"purchase_stream_{size}.csv",
        index=False
    )

    print(
        f"Generated {size:,} products, "
        f"{size:,} users and "
        f"{STREAM_LIMIT:,} purchase events"
    )

print("\nData preparation completed successfully!")
