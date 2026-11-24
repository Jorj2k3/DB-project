import time
from pathlib import Path

import numpy as np
import pandas as pd

from redis_loader import get_redis_client, load_scale
from leaderboard import increment_score, get_top_k, get_rank


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

DATASET_SIZES = [1000, 10000, 100000]

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
        ),
    }


def measure_operation(operation, arguments):
    latencies_ms = []

    # Warm-up phase
    for args in arguments[:WARMUP_OPERATIONS]:
        operation(*args)

    # Measurement phase
    for args in arguments[
        WARMUP_OPERATIONS : WARMUP_OPERATIONS + MEASURED_OPERATIONS
    ]:
        start = time.perf_counter_ns()
        operation(*args)
        end = time.perf_counter_ns()

        latencies_ms.append((end - start) / 1_000_000)

    return calculate_statistics(latencies_ms)


def benchmark_top_k(r):
    total_operations = WARMUP_OPERATIONS + MEASURED_OPERATIONS
    arguments = [(r, TOP_K) for _ in range(total_operations)]
    return measure_operation(get_top_k, arguments)


def generate_rank_workload(size):
    products = pd.read_csv(
        DATA_DIR / f"products_{size}.csv", usecols=["product_id"]
    )
    rng = np.random.default_rng(RANDOM_SEED)
    total_operations = WARMUP_OPERATIONS + MEASURED_OPERATIONS
    product_ids = rng.choice(
        products["product_id"].to_numpy(),
        size=total_operations,
        replace=True,
    )
    return [int(pid) for pid in product_ids]


def benchmark_rank_lookup(r, size):
    product_ids = generate_rank_workload(size)
    arguments = [(r, pid) for pid in product_ids]
    return measure_operation(get_rank, arguments)


def generate_update_workload(size):
    total_operations = WARMUP_OPERATIONS + MEASURED_OPERATIONS
    purchases = pd.read_csv(
        DATA_DIR / f"purchase_stream_{size}.csv",
        usecols=["product_id"],
        nrows=total_operations,
    )
    if len(purchases) < total_operations:
        raise ValueError("Not enough purchases for the benchmark")
    return [int(pid) for pid in purchases["product_id"]]


def benchmark_score_update(r, size):
    product_ids = generate_update_workload(size)
    arguments = [(r, pid) for pid in product_ids]
    return measure_operation(increment_score, arguments)


def get_total_sales(r):
    items = r.zrange("leaderboard:products", 0, -1, withscores=True)
    return int(sum(score for _, score in items))


def run_benchmarks():
    all_results = []

    for round_id in range(1, BENCHMARK_ROUNDS + 1):
        print("\n" + "#" * 60)
        print(f"REDIS BENCHMARK ROUND {round_id}/{BENCHMARK_ROUNDS}")
        print("#" * 60)

        for size in DATASET_SIZES:
            print("\n" + "=" * 60)
            print(f"Round: {round_id} | Dataset size: {size:,}")
            print("=" * 60)

            load_scale(size)
            r = get_redis_client()

            try:
                operations = [
                    ("top_k", lambda: benchmark_top_k(r)),
                    ("rank_lookup", lambda: benchmark_rank_lookup(r, size)),
                    ("score_update", lambda: benchmark_score_update(r, size)),
                ]

                for operation_name, benchmark in operations:
                    print(f"\nRunning {operation_name}...")

                    if operation_name == "score_update":
                        sales_before = get_total_sales(r)

                    statistics = benchmark()

                    if operation_name == "score_update":
                        sales_after = get_total_sales(r)
                        expected = WARMUP_OPERATIONS + MEASURED_OPERATIONS
                        assert (
                            sales_after - sales_before == expected
                        ), "Incorrect number of score updates"
                        print("[PASS] Score update validation")

                    all_results.append(
                        {
                            "database": "Redis",
                            "round": round_id,
                            "dataset_size": size,
                            "with_indexes": True,
                            "operation": operation_name,
                            **statistics,
                        }
                    )

                    print(f"Mean latency: {statistics['mean_ms']:.6f} ms")
                    print(f"P95 latency:  {statistics['p95_ms']:.6f} ms")
                    print(
                        f"Throughput:   {statistics['throughput_ops_sec']:.2f} ops/s"
                    )
            finally:
                r.close()

    return pd.DataFrame(all_results)


def save_results(results):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "redis_benchmark_rounds.csv"
    results.to_csv(output_path, index=False)
    print(f"\n[Redis] Results saved to {output_path}")


if __name__ == "__main__":
    results = run_benchmarks()
    save_results(results)

    print("\nREDIS BENCHMARK SUMMARY")
    print("=" * 90)
    print(
        results[
            [
                "dataset_size",
                "operation",
                "mean_ms",
                "p95_ms",
                "throughput_ops_sec",
            ]
        ].to_string(index=False)
    )
    print("\nAll Redis benchmarks completed!")