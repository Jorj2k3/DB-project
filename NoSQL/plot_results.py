from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
REDIS_FILE = RESULTS_DIR / "redis_benchmark_rounds.csv"
SQL_FILE = RESULTS_DIR / "sql_benchmark_rounds.csv"
PLOTS_DIR = RESULTS_DIR / "comparison_plots"

OPERATIONS = {
    "top_k": "Top-K Retrieval",
    "rank_lookup": "Rank Lookup",
    "score_update": "Score Update",
}

METRICS = [
    ("mean_ms", "Average latency (ms)", "mean_latency"),
    ("p95_ms", "Mean P95 latency (ms)", "p95_latency"),
    ("throughput_ops_sec", "Throughput (operations/s)", "throughput"),
]

STYLES = {
    "PostgreSQL (No Index)": {"color": "#9999A5", "marker": "s"},
    "PostgreSQL (With Index)": {"color": "#9575CD", "marker": "o"},
    "Redis (ZSET)": {"color": "#D82C20", "marker": "^"},
}


def load_combined_results():
    frames = []

    if REDIS_FILE.exists():
        redis_df = pd.read_csv(REDIS_FILE)
        redis_df["series"] = "Redis (ZSET)"
        frames.append(redis_df)

    if SQL_FILE.exists():
        sql_df = pd.read_csv(SQL_FILE)
        sql_df["series"] = sql_df["with_indexes"].map(
            {
                False: "PostgreSQL (No Index)",
                True: "PostgreSQL (With Index)",
            }
        )
        frames.append(sql_df)

    if not frames:
        raise FileNotFoundError("No benchmark CSV files found in results/.")

    return pd.concat(frames, ignore_index=True)


def aggregate_results(df):
    metric_cols = ["mean_ms", "median_ms", "p95_ms", "p99_ms", "throughput_ops_sec"]
    grouped = df.groupby(["series", "dataset_size", "operation"])
    agg = grouped[metric_cols].agg(["mean", "std"])
    agg.columns = [f"{m}_{s}" for m, s in agg.columns]
    return agg.reset_index()


def plot_comparisons(agg):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    for metric, ylabel, filename in METRICS:
        mean_col = f"{metric}_mean"
        std_col = f"{metric}_std"

        for op_key, op_title in OPERATIONS.items():
            op_df = agg[agg["operation"] == op_key]
            fig, ax = plt.subplots(figsize=(8, 5))

            for series_name, style in STYLES.items():
                subset = op_df[op_df["series"] == series_name].sort_values(
                    "dataset_size"
                )
                if subset.empty:
                    continue

                ax.errorbar(
                    subset["dataset_size"],
                    subset[mean_col],
                    yerr=subset[std_col],
                    marker=style["marker"],
                    markersize=7,
                    linewidth=2,
                    elinewidth=1.5,
                    capsize=5,
                    capthick=1.5,
                    color=style["color"],
                    label=series_name,
                )

            ax.set_title(
                f"{op_title} — PostgreSQL vs. Redis",
                fontsize=15,
                fontweight="bold",
            )
            ax.set_xlabel("Number of products", fontsize=12)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_xscale("log")
            ax.set_xticks([1000, 10000, 100000])
            ax.set_xticklabels(["1k", "10k", "100k"])
            ax.set_ylim(bottom=0)
            ax.grid(True, linestyle="--", alpha=0.3)
            ax.legend()

            fig.text(
                0.5,
                0.01,
                "Mean ± standard deviation across 5 benchmark rounds",
                ha="center",
                fontsize=9,
                color="#666666",
            )
            fig.tight_layout(rect=[0, 0.04, 1, 1])

            out_path = PLOTS_DIR / f"{op_key}_{filename}.png"
            fig.savefig(out_path, dpi=300, bbox_inches="tight")
            plt.close(fig)
            print(f"[PLOT] Saved {out_path.name}")


if __name__ == "__main__":
    combined = load_combined_results()
    aggregated = aggregate_results(combined)

    summary_path = RESULTS_DIR / "comparison_aggregated.csv"
    aggregated.to_csv(summary_path, index=False)
    print(f"[SUMMARY] Saved {summary_path}\n")

    print(
        aggregated[
            [
                "series",
                "dataset_size",
                "operation",
                "mean_ms_mean",
                "p95_ms_mean",
                "throughput_ops_sec_mean",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    print()
    plot_comparisons(aggregated)