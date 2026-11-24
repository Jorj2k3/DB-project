import time
import random
import argparse
import threading

from pathlib import Path
from decimal import Decimal
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from SQL.sql_loader import get_pg_conn, load_scale
from SQL.leaderboard import (
    get_top_k,
    get_rank,
    record_purchase
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

DATASET_SIZES = [1000, 10000, 100000]
CLIENT_COUNTS = [1, 5, 10, 20, 50]
INDEX_CONFIGURATIONS = [False, True]

TOTAL_REQUESTS = 10000
SIMULATION_ROUNDS = 5
RANDOM_SEED = 42
TOP_K = 10

TOP_K_RATIO = 0.7
RANK_RATIO = 0.2

def generate_workload(size, total_requests, seed):

    rng = random.Random(seed)

    products = pd.read_csv(
        DATA_DIR / f"products_{size}.csv"
    )

    purchases = pd.read_csv(
        DATA_DIR / f"purchase_stream_{size}.csv"
    )

    product_ids = products["product_id"].astype(int).tolist()

    top_k_count = int(total_requests * TOP_K_RATIO)
    rank_count = int(total_requests * RANK_RATIO)

    purchase_count = (
        total_requests - top_k_count - rank_count
    )

    if purchase_count > len(purchases):
        raise ValueError(
            "Not enough purchase events in the purchase stream."
        )

    workload = []

    # Top-K requests

    for _ in range(top_k_count):

        workload.append(
            ("top_k", (TOP_K,))
        )

    # Rank lookup requests

    for _ in range(rank_count):

        product_id = rng.choice(product_ids)

        workload.append(
            ("rank_lookup", (product_id,))
        )

    # Purchase requests

    for purchase in purchases.head(
        purchase_count
    ).itertuples(index=False):

        workload.append((
            "purchase",
            (
                int(purchase.user_id),
                int(purchase.product_id),
                Decimal(str(purchase.price)),
                pd.Timestamp(
                    purchase.event_time
                ).to_pydatetime()
            )
        ))

    # Randomize the order of operations

    rng.shuffle(workload)

    return workload

def execute_request(conn, operation, arguments):

    if operation == "top_k":

        get_top_k(conn, *arguments)

    elif operation == "rank_lookup":

        get_rank(conn, *arguments)

    elif operation == "purchase":

        record_purchase(conn, *arguments)

    else:

        raise ValueError(
            f"Unknown operation: {operation}"
        )

    # Ensure that no transaction remains open.

    conn.commit()

def simulate_client(conn, requests, start_event):

    results = []

    start_event.wait()

    for operation, arguments in requests:

        start = time.perf_counter_ns()

        execute_request(
            conn,
            operation,
            arguments
        )

        end = time.perf_counter_ns()

        latency_ms = (
            end - start
        ) / 1_000_000

        results.append({
            "operation": operation,
            "latency_ms": latency_ms
        })

    return results

def get_database_state():

    conn = get_pg_conn()

    try:

        with conn.cursor() as cur:

            cur.execute("""
                SELECT COALESCE(SUM(sales_count), 0)
                FROM products;
            """)

            total_sales = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM purchases;
            """)

            purchase_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COALESCE(SUM(total_spent), 0)
                FROM users;
            """)

            total_spent = cur.fetchone()[0]

        return {
            "total_sales": total_sales,
            "purchase_count": purchase_count,
            "total_spent": total_spent
        }

    finally:

        conn.close()


def validate_simulation(before, after, workload):

    purchases = [
        arguments
        for operation, arguments in workload
        if operation == "purchase"
    ]

    expected_purchases = len(purchases)

    expected_spent = sum(
        (arguments[2] for arguments in purchases),
        Decimal("0.00")
    )

    sales_difference = (
        after["total_sales"]
        - before["total_sales"]
    )

    purchases_difference = (
        after["purchase_count"]
        - before["purchase_count"]
    )

    spent_difference = (
        after["total_spent"]
        - before["total_spent"]
    )

    if sales_difference != expected_purchases:

        raise AssertionError(
            "Incorrect total sales count."
        )

    if purchases_difference != expected_purchases:

        raise AssertionError(
            "Incorrect number of purchases."
        )

    if spent_difference != expected_spent:

        raise AssertionError(
            "Incorrect total amount spent."
        )

    print("[Validation] All aggregate checks passed.")

def run_simulation(workload, client_count):

    if client_count < 1:
        raise ValueError("At least one client is required.")

    if client_count > len(workload):
        raise ValueError("Too many clients.")

    client_workloads = [
        workload[i::client_count]
        for i in range(client_count)
    ]

    start_event = threading.Event()

    connections = []
    results = []

    try:

        # Create one persistent connection per client.

        for _ in range(client_count):

            connections.append(
                get_pg_conn()
            )

        with ThreadPoolExecutor(
            max_workers=client_count
        ) as executor:

            futures = [
                executor.submit(
                    simulate_client,
                    connections[i],
                    client_workloads[i],
                    start_event
                )
                for i in range(client_count)
            ]

            start = time.perf_counter()

            # Allow all clients to start executing.

            start_event.set()

            for future in futures:

                results.extend(
                    future.result()
                )

            elapsed = (
                time.perf_counter() - start
            )

    finally:

        for conn in connections:

            conn.close()

    return results, elapsed

def calculate_statistics(
    results,
    elapsed,
    size,
    client_count,
    with_indexes,
    round_number
):

    df = pd.DataFrame(results)

    statistics = []

    operations = [
        "all",
        "top_k",
        "rank_lookup",
        "purchase"
    ]

    for operation in operations:

        if operation == "all":

            latencies = df["latency_ms"].to_numpy()

        else:

            latencies = df.loc[
                df["operation"] == operation,
                "latency_ms"
            ].to_numpy()

        if len(latencies) == 0:
            continue

        statistics.append({
            "database": "PostgreSQL",
            "round": round_number,
            "dataset_size": size,
            "with_indexes": with_indexes,
            "concurrent_clients": client_count,
            "operation": operation,
            "requests": len(latencies),

            "mean_ms": np.mean(latencies),
            "median_ms": np.median(latencies),
            "min_ms": np.min(latencies),
            "max_ms": np.max(latencies),
            "std_ms": np.std(latencies),

            "p95_ms": np.percentile(
                latencies, 95
            ),

            "p99_ms": np.percentile(
                latencies, 99
            ),

            "elapsed_sec": elapsed,

            "throughput_ops_sec": (
                len(latencies) / elapsed
            )
        })

    return statistics

def run_experiments(
    dataset_sizes,
    client_counts,
    total_requests,
    rounds
):

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        RESULTS_DIR / "sql_simulation_rounds.csv"
    )

    all_results = []

    for size in dataset_sizes:

        for client_count in client_counts:

            for round_number in range(
                1, rounds + 1
            ):

                workload = generate_workload(
                    size,
                    total_requests,
                    RANDOM_SEED + round_number
                )

                print(
                    f"\nWorkload: "
                    f"{Counter(op for op, _ in workload)}"
                )

                configurations = (
                    INDEX_CONFIGURATIONS
                    if round_number % 2 == 1
                    else INDEX_CONFIGURATIONS[::-1]
                )

                for with_indexes in configurations:

                    print("\n" + "=" * 60)

                    print(f"Dataset size: {size:,}")
                    print(f"Clients: {client_count}")
                    print(f"Round: {round_number}")
                    print(f"Indexes: {with_indexes}")
                    print(f"Requests: {total_requests:,}")

                    # Reset the database.

                    load_scale(
                        size,
                        with_indexes=with_indexes
                    )

                    before = get_database_state()

                    # Execute concurrent requests.

                    results, elapsed = run_simulation(
                        workload,
                        client_count
                    )

                    after = get_database_state()

                    if len(results) != len(workload):

                        raise AssertionError(
                            "Not all requests were completed."
                        )

                    validate_simulation(
                        before,
                        after,
                        workload
                    )

                    statistics = calculate_statistics(
                        results,
                        elapsed,
                        size,
                        client_count,
                        with_indexes,
                        round_number
                    )

                    all_results.extend(statistics)

                    overall = next(
                        row for row in statistics
                        if row["operation"] == "all"
                    )

                    print(
                        f"Elapsed: "
                        f"{elapsed:.3f} s"
                    )

                    print(
                        f"Mean latency: "
                        f"{overall['mean_ms']:.3f} ms"
                    )

                    print(
                        f"P95 latency: "
                        f"{overall['p95_ms']:.3f} ms"
                    )

                    print(
                        f"Throughput: "
                        f"{overall['throughput_ops_sec']:.2f} "
                        f"requests/s"
                    )

                    # Save progress after each experiment.

                    pd.DataFrame(all_results).to_csv(
                        output_file,
                        index=False
                    )

    print("\nSimulation completed.")
    print(f"Results saved to: {output_file}")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Online Shopping Workload Simulator"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a small simulation for testing"
    )

    args = parser.parse_args()

    if args.quick:

        run_experiments(
            dataset_sizes=[1000],
            client_counts=[1, 5],
            total_requests=1000,
            rounds=1
        )

    else:

        run_experiments(
            dataset_sizes=DATASET_SIZES,
            client_counts=CLIENT_COUNTS,
            total_requests=TOTAL_REQUESTS,
            rounds=SIMULATION_ROUNDS
        )