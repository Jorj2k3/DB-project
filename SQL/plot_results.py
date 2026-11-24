from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

INPUT_FILE = RESULTS_DIR / "sql_benchmark_rounds.csv"
AGGREGATED_FILE = RESULTS_DIR / "sql_benchmark_aggregated.csv"
PLOTS_DIR = RESULTS_DIR / "final_plots"

OPERATIONS = {
    "top_k": "Top-K Retrieval",
    "rank_lookup": "Rank Lookup",
    "score_update": "Score Update"
}

COLORS = {
    False: "#9999A5",
    True: "#9575CD"
}

MARKERS = {
    False: "s",
    True: "o"
}

METRICS = [
    "mean_ms",
    "median_ms",
    "p95_ms",
    "p99_ms",
    "throughput_ops_sec"
]

GROUP_COLUMNS = [
    "database",
    "dataset_size",
    "with_indexes",
    "operation"
]

def plot_metric(results, metric, ylabel, filename):

    for operation, title in OPERATIONS.items():

        operation_results = results[
            results["operation"] == operation
        ]

        fig, ax = plt.subplots(figsize=(8, 5))

        for with_indexes in [False, True]:

            subset = operation_results[
                operation_results["with_indexes"] == with_indexes
            ].sort_values("dataset_size")

            label = (
                "With secondary index"
                if with_indexes
                else "Without secondary index"
            )

            ax.plot(
                subset["dataset_size"],
                subset[metric],
                marker="o",
                markersize=7,
                linewidth=2,
                color=COLORS[with_indexes],
                label=label
            )

        ax.set_title(title, fontsize=16, fontweight="bold")
        ax.set_xlabel("Number of products", fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)

        ax.set_xscale("log")
        ax.set_xticks([1000, 10000, 100000])
        ax.set_xticklabels(["1k", "10k", "100k"])

        ax.set_ylim(bottom=0)

        ax.grid(
            True,
            linestyle="--",
            alpha=0.3
        )

        ax.legend()
        fig.tight_layout()

        output_path = (
            PLOTS_DIR / f"{operation}_{filename}.png"
        )

        fig.savefig(
            output_path,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(fig)

        print(f"[PLOT] Saved {output_path.name}")

def aggregate_results(results):

    grouped = results.groupby(GROUP_COLUMNS)

    aggregated = grouped[METRICS].agg(
        ["mean", "std", "median"]
    )

    # Flatten multi-level column names
    aggregated.columns = [
        f"{metric}_{statistic}"
        for metric, statistic in aggregated.columns
    ]

    aggregated["rounds"] = grouped["round"].nunique()

    aggregated["total_operations"] = (
        grouped["operations"].sum()
    )

    return aggregated.reset_index()

def plot_metric(results, metric, ylabel, filename):

    mean_column = f"{metric}_mean"
    std_column = f"{metric}_std"

    for operation, title in OPERATIONS.items():

        operation_results = results[
            results["operation"] == operation
        ]

        fig, ax = plt.subplots(figsize=(8, 5))

        for with_indexes in [False, True]:

            subset = operation_results[
                operation_results["with_indexes"] == with_indexes
            ].sort_values("dataset_size")

            label = (
                "With secondary index"
                if with_indexes
                else "Without secondary index"
            )

            ax.errorbar(
                subset["dataset_size"],
                subset[mean_column],
                yerr=subset[std_column],
                marker=MARKERS[with_indexes],
                markersize=7,
                linewidth=2,
                elinewidth=1.5,
                capsize=5,
                capthick=1.5,
                color=COLORS[with_indexes],
                label=label
            )

        ax.set_title(
            title,
            fontsize=16,
            fontweight="bold"
        )

        ax.set_xlabel(
            "Number of products",
            fontsize=12
        )

        ax.set_ylabel(
            ylabel,
            fontsize=12
        )

        ax.set_xscale("log")

        ax.set_xticks([1000, 10000, 100000])
        ax.set_xticklabels(["1k", "10k", "100k"])

        upper_limit = (
            operation_results[mean_column]
            + operation_results[std_column]
        ).max()

        ax.set_ylim(
            bottom=0,
            top=upper_limit * 1.15
        )

        ax.grid(
            True,
            linestyle="--",
            alpha=0.3
        )

        ax.legend()

        fig.text(
            0.5,
            0.01,
            "Mean ± standard deviation across 5 benchmark rounds",
            ha="center",
            fontsize=9,
            color="#666666"
        )

        fig.tight_layout(rect=[0, 0.04, 1, 1])

        output_path = (
            PLOTS_DIR / f"{operation}_{filename}.png"
        )

        fig.savefig(
            output_path,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(fig)

        print(f"[PLOT] Saved {output_path.name}")


if __name__ == "__main__":

    PLOTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Load individual benchmark rounds
    results = pd.read_csv(INPUT_FILE)

    # Validate benchmark results
    assert len(results) == 90, \
        "Incorrect number of benchmark results"

    assert not results.duplicated(
        GROUP_COLUMNS + ["round"]
    ).any(), "Duplicate benchmark rounds"

    assert (results["operations"] == 1000).all(), \
        "Incorrect number of measured operations"

    # Aggregate results across rounds
    aggregated = aggregate_results(results)

    assert len(aggregated) == 18, \
        "Incorrect number of configurations"

    assert (aggregated["rounds"] == 5).all(), \
        "Missing benchmark rounds"

    # Save aggregated statistics
    aggregated.to_csv(
        AGGREGATED_FILE,
        index=False
    )

    print(f"[SQL] Aggregated results saved to {AGGREGATED_FILE}")

    # Generate performance plots
    plot_metric(
        aggregated,
        metric="mean_ms",
        ylabel="Average latency (ms)",
        filename="mean_latency"
    )

    plot_metric(
        aggregated,
        metric="p95_ms",
        ylabel="Mean P95 latency (ms)",
        filename="p95_latency"
    )

    plot_metric(
        aggregated,
        metric="throughput_ops_sec",
        ylabel="Throughput (operations/s)",
        filename="throughput"
    )

    print("\nAll final SQL performance plots generated!")