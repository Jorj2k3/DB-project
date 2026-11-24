from pathlib import Path
from decimal import Decimal
import pandas as pd

from sql_loader import get_pg_conn
from leaderboard import record_purchase, get_top_k, get_rank

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_state(conn, user_id, product_id):
    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT sales_count
                FROM products
                WHERE product_id = %s;
            """, (product_id,))

            sales_count = cur.fetchone()[0]

            cur.execute("""
                SELECT total_spent
                FROM users
                WHERE user_id = %s;
            """, (user_id,))

            total_spent = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM purchases;")

            purchase_count = cur.fetchone()[0]

    return sales_count, total_spent, purchase_count


def test_record_purchase():

    # 1. Read the first purchase event

    stream = pd.read_csv(
        DATA_DIR / "purchase_stream_1000.csv"
    )

    purchase = stream.iloc[0]

    user_id = int(purchase["user_id"])
    product_id = int(purchase["product_id"])
    price = Decimal(str(purchase["price"]))
    event_time = purchase["event_time"]

    print("\nPURCHASE EVENT")
    print(f"User ID: {user_id}")
    print(f"Product ID: {product_id}")
    print(f"Price: {price}")
    print(f"Event time: {event_time}")

    conn = get_pg_conn()

    try:

        # 2. Get initial database state

        before = get_state(conn, user_id, product_id)

        print("\nBEFORE PURCHASE")
        print(f"Sales count: {before[0]}")
        print(f"Total spent: {before[1]}")
        print(f"Purchase count: {before[2]}")

        # 3. Record purchase

        record_purchase(
            conn,
            user_id,
            product_id,
            price,
            event_time
        )

        # 4. Get updated database state

        after = get_state(conn, user_id, product_id)

        print("\nAFTER PURCHASE")
        print(f"Sales count: {after[0]}")
        print(f"Total spent: {after[1]}")
        print(f"Purchase count: {after[2]}")

        # 5. Validate results

        assert after[0] == before[0] + 1, \
            "Sales count was not updated correctly"

        assert after[1] == before[1] + price, \
            "Total spent was not updated correctly"

        assert after[2] == before[2] + 1, \
            "Purchase was not recorded correctly"

        print("\n[PASS] Product sales count updated")
        print("[PASS] User total spent updated")
        print("[PASS] Purchase recorded")

        print("\nAll tests passed!")

    finally:
        conn.close()

def test_get_top_k():

    conn = get_pg_conn()

    try:
        k = 10
        results = get_top_k(conn, k)

        print("\nTOP 10 PRODUCTS")
        print("-" * 75)

        for rank, (product_id, name, score) in enumerate(
            results, start=1
        ):
            print(
                f"{rank:>2}. {product_id:<10} "
                f"{name:<40} {score:>6}"
            )

        # Validate number of returned products
        assert len(results) == k, \
            "Incorrect number of products"

        # Validate descending order and tie-breaking
        for i in range(len(results) - 1):

            current_id = results[i][0]
            current_score = results[i][2]

            next_id = results[i + 1][0]
            next_score = results[i + 1][2]

            assert (current_score, current_id) >= (
                next_score, next_id
            ), "Incorrect leaderboard order"

        # Validate unique products
        product_ids = [row[0] for row in results]

        assert len(set(product_ids)) == k, \
            "Duplicate products in leaderboard"

        print("\n[PASS] Correct number of products")
        print("[PASS] Correct leaderboard order")
        print("[PASS] No duplicate products")

        print("\nAll Top-K tests passed!")

    finally:
        conn.close()

def test_get_rank():

    conn = get_pg_conn()

    try:
        top_products = get_top_k(conn, 10)

        print("\nRANK LOOKUP TEST")
        print("-" * 75)

        for expected_rank, product in enumerate(
            top_products, start=1
        ):
            product_id, name, score = product

            actual_rank = get_rank(conn, product_id)

            print(
                f"Product: {name:<35} "
                f"Expected: {expected_rank:<3} "
                f"Actual: {actual_rank}"
            )

            assert actual_rank == expected_rank, \
                f"Incorrect rank for product {product_id}"

        print("\n[PASS] Correct ranks for Top 10 products")

        # Test a nonexistent product

        result = get_rank(conn, -1)

        assert result is None, \
            "Nonexistent product should return None"

        print("[PASS] Nonexistent product handled correctly")

        print("\nAll Rank Lookup tests passed!")

    finally:
        conn.close()


if __name__ == "__main__":
    # test_record_purchase()
    # test_get_top_k()
    test_get_rank()