import time
from pathlib import Path

import numpy as np
import pandas as pd

from sql_loader import get_pg_conn, load_scale
from leaderboard import increment_score, get_top_k, get_rank


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

DATASET_SIZES = [1000, 10000, 100000]
INDEX_CONFIGURATIONS = [False, True]

WARMUP_OPERATIONS = 100
MEASURED_OPERATIONS = 1000

TOP_K = 10
RANDOM_SEED = 42

BENCHMARK_ROUNDS = 5

def calculate_statistics(latencies_ms):

    latencies = np.array(latencies_ms, dtype=float)

    return {
        "operations": len(latencies),
        "mean_ms": float(np.mean(latencies)),
        "median_ms": float(np.median(latencies)),
        "min_ms": float(np.min(latencies)),
        "max_ms": float(np.max(latencies)),
        "std_ms": float(np.std(latencies)),
        "p95_ms": float(np.percentile(latencies, 95)),
        "p99_ms": float(np.percentile(latencies, 99)),
        "throughput_ops_sec": float(
            len(latencies) / (np.sum(latencies) / 1000)
        )
    }

def measure_operation(operation, arguments):

    latencies_ms = []

    # Warm-up phase
    for args in arguments[:WARMUP_OPERATIONS]:
        operation(*args)

    # Measurement phase
    for args in arguments[
        WARMUP_OPERATIONS:
        WARMUP_OPERATIONS + MEASURED_OPERATIONS
    ]:
        start = time.perf_counter_ns()

        operation(*args)

        end = time.perf_counter_ns()

        latency_ms = (end - start) / 1_000_000
        latencies_ms.append(latency_ms)

    return calculate_statistics(latencies_ms)

def benchmark_top_k(conn):

    total_operations = (
        WARMUP_OPERATIONS + MEASURED_OPERATIONS
    )

    arguments = [
        (conn, TOP_K)
        for _ in range(total_operations)
    ]

    return measure_operation(get_top_k, arguments)

def generate_rank_workload(size):

    products = pd.read_csv(
        DATA_DIR / f"products_{size}.csv",
        usecols=["product_id"]
    )

    rng = np.random.default_rng(RANDOM_SEED)

    total_operations = (
        WARMUP_OPERATIONS + MEASURED_OPERATIONS
    )

    product_ids = rng.choice(
        products["product_id"].to_numpy(),
        size=total_operations,
        replace=True
    )

    return [int(product_id) for product_id in product_ids]

def benchmark_rank_lookup(conn, size):

    product_ids = generate_rank_workload(size)

    arguments = [
        (conn, product_id)
        for product_id in product_ids
    ]

    return measure_operation(get_rank, arguments)

def generate_update_workload(size):

    total_operations = (
        WARMUP_OPERATIONS + MEASURED_OPERATIONS
    )

    purchases = pd.read_csv(
        DATA_DIR / f"purchase_stream_{size}.csv",
        usecols=["product_id"],
        nrows=total_operations
    )

    if len(purchases) < total_operations:
        raise ValueError(
            "Not enough purchases for the benchmark"
        )

    return [
        int(product_id)
        for product_id in purchases["product_id"]
    ]


def benchmark_score_update(conn, size):

    product_ids = generate_update_workload(size)

    arguments = [
        (conn, product_id)
        for product_id in product_ids
    ]

    return measure_operation(
        increment_score,
        arguments
    )

def get_total_sales(conn):

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT SUM(sales_count)
                FROM products;
            """)

            return cur.fetchone()[0]
        
def run_benchmarks():

    all_results = []

    for round_id in range(1, BENCHMARK_ROUNDS + 1):

        print("\n" + "#" * 60)
        print(f"BENCHMARK ROUND {round_id}/{BENCHMARK_ROUNDS}")
        print("#" * 60)

        # Alternate index configuration order
        configurations = (
            INDEX_CONFIGURATIONS
            if round_id % 2 == 1
            else INDEX_CONFIGURATIONS[::-1]
        )

        for size in DATASET_SIZES:

            for with_indexes in configurations:

                print("\n" + "=" * 60)
                print(f"Round: {round_id}")
                print(f"Dataset size: {size:,}")
                print(f"Secondary indexes: {with_indexes}")
                print("=" * 60)

                load_scale(
                    size,
                    with_indexes=with_indexes
                )

                conn = get_pg_conn()

                try:
                    operations = [
                        (
                            "top_k",
                            lambda: benchmark_top_k(conn)
                        ),
                        (
                            "rank_lookup",
                            lambda: benchmark_rank_lookup(
                                conn, size
                            )
                        ),
                        (
                            "score_update",
                            lambda: benchmark_score_update(
                                conn, size
                            )
                        )
                    ]

                    for operation_name, benchmark in operations:

                        print(f"\nRunning {operation_name}...")

                        if operation_name == "score_update":
                            sales_before = get_total_sales(conn)

                        statistics = benchmark()

                        if operation_name == "score_update":

                            sales_after = get_total_sales(conn)

                            expected_increase = (
                                WARMUP_OPERATIONS
                                + MEASURED_OPERATIONS
                            )

                            assert (
                                sales_after - sales_before
                                == expected_increase
                            ), "Incorrect number of score updates"

                            print("[PASS] Score update validation")

                        result = {
                            "database": "PostgreSQL",
                            "round": round_id,
                            "dataset_size": size,
                            "with_indexes": with_indexes,
                            "operation": operation_name,
                            **statistics
                        }

                        all_results.append(result)

                        print(
                            f"Mean latency: "
                            f"{statistics['mean_ms']:.6f} ms"
                        )

                        print(
                            f"P95 latency: "
                            f"{statistics['p95_ms']:.6f} ms"
                        )

                        print(
                            f"Throughput: "
                            f"{statistics['throughput_ops_sec']:.2f} ops/s"
                        )

                finally:
                    conn.close()

    return pd.DataFrame(all_results)

def save_results(results):

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = RESULTS_DIR / "sql_benchmark_rounds.csv"

    results.to_csv(
        output_path,
        index=False
    )

    print(f"\n[SQL] Results saved to {output_path}")

if __name__ == "__main__":

    results = run_benchmarks()

    save_results(results)

    print("\nBENCHMARK SUMMARY")
    print("=" * 100)

    print(
        results[
            [
                "dataset_size",
                "with_indexes",
                "operation",
                "mean_ms",
                "p95_ms",
                "throughput_ops_sec"
            ]
        ].to_string(index=False)
    )

    print("\nAll SQL benchmarks completed!")