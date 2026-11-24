
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_PATH = DATA_DIR / "2019-Oct.csv"

CHUNK_SIZE = 500_000

total_events = 0
total_purchases = 0

unique_products = set()
unique_users = set()
purchased_products = set()
unique_buyers = set()

event_counts = {}

print("Analyzing dataset...")

for i, chunk in enumerate(
    pd.read_csv(
        RAW_PATH,
        chunksize=CHUNK_SIZE,
        usecols=["event_type", "product_id", "user_id"]
    ),
    start=1
):
    total_events += len(chunk)

    unique_products.update(
        chunk["product_id"].dropna().unique()
    )

    unique_users.update(
        chunk["user_id"].dropna().unique()
    )

    for event, count in chunk["event_type"].value_counts().items():
        event_counts[event] = event_counts.get(event, 0) + int(count)

    purchases = chunk[chunk["event_type"] == "purchase"]

    total_purchases += len(purchases)

    purchased_products.update(
        purchases["product_id"].dropna().unique()
    )

    unique_buyers.update(
        purchases["user_id"].dropna().unique()
    )

    print(f"Chunk {i}: {total_events:,} events processed")

print("\n--- DATASET STATISTICS ---")

print(f"Total events: {total_events:,}")
print(f"Unique products: {len(unique_products):,}")
print(f"Unique users: {len(unique_users):,}")
print(f"Total purchases: {total_purchases:,}")
print(f"Purchased products: {len(purchased_products):,}")
print(f"Unique buyers: {len(unique_buyers):,}")

print("\nEvent distribution:")

for event, count in event_counts.items():
    percentage = count / total_events * 100
    print(f"{event}: {count:,} ({percentage:.2f}%)")
