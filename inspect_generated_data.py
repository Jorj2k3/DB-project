from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

DATASET_SIZES = [1000, 10000, 100000]
STREAM_LIMIT = 15000


def inspect_csv(df, filename):
    print(f"\n--- {filename} ---")
    print(f"Number of rows: {len(df):,}")

    print("\nFirst 5 rows:")
    print(df.head().to_string(index=False))

    print("\nData types:")
    print(df.dtypes)

    print("\nMissing values:")
    print(df.isnull().sum())


def check(description, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    return bool(condition)


all_checks = []

for size in DATASET_SIZES:

    print("\n" + "=" * 70)
    print(f"DATASET SIZE: {size:,}")
    print("=" * 70)

    products = pd.read_csv(
        DATA_DIR / f"products_{size}.csv"
    )

    users = pd.read_csv(
        DATA_DIR / f"users_{size}.csv"
    )

    purchases = pd.read_csv(
        DATA_DIR / f"purchase_stream_{size}.csv"
    )

    checks = []

    # 1. Inspect products

    inspect_csv(products, f"products_{size}.csv")

    print("\nProduct validation:")

    checks.append(check(
        "Correct number of products",
        len(products) == size
    ))

    checks.append(check(
        "No duplicate product IDs",
        products["product_id"].is_unique
    ))

    checks.append(check(
        "No missing values",
        not products.isnull().any().any()
    ))

    checks.append(check(
        "No negative prices",
        (products["price"] >= 0).all()
    ))

    checks.append(check(
        "No negative sales counts",
        (products["sales_count"] >= 0).all()
    ))

    print(
        f"\nProducts with zero sales: "
        f"{(products['sales_count'] == 0).sum():,}"
    )

    print(
        f"Products with sales: "
        f"{(products['sales_count'] > 0).sum():,}"
    )

    print("\nSales count statistics:")
    print(products["sales_count"].describe())

    print("\nTop 5 best-selling products:")
    print(
        products.nlargest(5, "sales_count")[
            ["product_id", "product_name", "sales_count"]
        ].to_string(index=False)
    )

    # 2. Inspect users

    inspect_csv(users, f"users_{size}.csv")

    print("\nUser validation:")

    checks.append(check(
        "Correct number of users",
        len(users) == size
    ))

    checks.append(check(
        "No duplicate user IDs",
        users["user_id"].is_unique
    ))

    checks.append(check(
        "No missing values",
        not users.isnull().any().any()
    ))

    checks.append(check(
        "No negative total spent",
        (users["total_spent"] >= 0).all()
    ))

    print(
        f"\nUsers with zero spending: "
        f"{(users['total_spent'] == 0).sum():,}"
    )

    print("\nTotal spent statistics:")
    print(users["total_spent"].describe())

    # 3. Inspect purchase stream

    inspect_csv(
        purchases,
        f"purchase_stream_{size}.csv"
    )

    print("\nPurchase stream validation:")

    checks.append(check(
        "Correct number of purchases",
        len(purchases) == STREAM_LIMIT
    ))

    checks.append(check(
        "No missing values",
        not purchases.isnull().any().any()
    ))

    checks.append(check(
        "No negative purchase prices",
        (purchases["price"] >= 0).all()
    ))

    checks.append(check(
        "Valid timestamps",
        pd.to_datetime(
            purchases["event_time"],
            errors="coerce",
            utc=True
        ).notna().all()
    ))

    # 4. Validate foreign key references

    valid_products = purchases["product_id"].isin(
        products["product_id"]
    )

    valid_users = purchases["user_id"].isin(
        users["user_id"]
    )

    valid_purchases = valid_products & valid_users

    print("\nReferential integrity:")

    checks.append(check(
        "All product IDs exist",
        valid_products.all()
    ))

    checks.append(check(
        "All user IDs exist",
        valid_users.all()
    ))

    print(
        f"\nMissing product references: "
        f"{(~valid_products).sum():,}"
    )

    print(
        f"Missing user references: "
        f"{(~valid_users).sum():,}"
    )

    print(
        f"Valid purchases: "
        f"{valid_purchases.sum():,} / {len(purchases):,}"
    )

    print(
        f"Invalid purchases: "
        f"{(~valid_purchases).sum():,}"
    )

    print(
        f"Unique purchased products: "
        f"{purchases['product_id'].nunique():,}"
    )

    print(
        f"Unique buyers: "
        f"{purchases['user_id'].nunique():,}"
    )

    # 5. Dataset validation summary

    dataset_valid = all(checks)
    all_checks.append(dataset_valid)

    print("\n" + "-" * 70)

    if dataset_valid:
        print(f"DATASET {size:,}: VALID")
    else:
        print(f"DATASET {size:,}: INVALID")

    print("-" * 70)


# 6. Final validation summary

print("\n" + "=" * 70)
print("FINAL VALIDATION SUMMARY")
print("=" * 70)

for size, valid in zip(DATASET_SIZES, all_checks):
    status = "PASS" if valid else "FAIL"
    print(f"Dataset {size:>7,}: {status}")

if all(all_checks):
    print("\nAll datasets passed validation!")
else:
    print("\nSome datasets failed validation!")