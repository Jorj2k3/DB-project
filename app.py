import time
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

import streamlit as st
import pandas as pd

from SQL.sql_loader import get_pg_conn, load_scale
from SQL.leaderboard import (
    get_top_k,
    get_rank,
    get_product,
    record_purchase
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

DATASET_SIZES = [1000, 10000, 100000]


st.set_page_config(
    page_title="Online Shopping Leaderboard",
    page_icon="🏆",
    layout="wide"
)

st.title("Online Shopping Leaderboard")

st.caption(
    "Database Systems — PostgreSQL & Redis"
)

def execute_operation(operation, *args):

    conn = get_pg_conn()

    try:

        start = time.perf_counter_ns()

        result = operation(conn, *args)

        end = time.perf_counter_ns()

        latency_ms = (end - start) / 1_000_000

        return result, latency_ms

    finally:
        conn.close()


def get_database_statistics(conn):

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    COUNT(*),
                    COALESCE(SUM(sales_count), 0)
                FROM products;
            """)

            product_count, total_sales = cur.fetchone()

            cur.execute("""
                SELECT COUNT(*) FROM users;
            """)

            user_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM purchases;
            """)

            purchase_count = cur.fetchone()[0]

            return {
                "products": product_count,
                "users": user_count,
                "total_sales": total_sales,
                "purchases": purchase_count
            }


@st.cache_data
def load_purchase_stream(size):

    return pd.read_csv(
        DATA_DIR / f"purchase_stream_{size}.csv"
    )


def display_product(product):

    product_id, name, category, brand, price, sales = product

    st.subheader(name)

    col1, col2, col3 = st.columns(3)

    col1.metric("Product ID", str(product_id))
    col2.metric("Price", f"{price:,.2f}")
    col3.metric("Sales count", f"{sales:,}")

    st.write(f"**Category:** {category}")
    st.write(f"**Brand:** {brand}")

st.sidebar.header("Database Configuration")

st.sidebar.selectbox(
    "Database",
    options=["PostgreSQL"]
)

dataset_size = st.sidebar.selectbox(
    "Dataset size",
    options=DATASET_SIZES,
    format_func=lambda size: f"{size:,} products"
)

with_indexes = st.sidebar.checkbox(
    "Enable secondary index",
    value=True
)

st.sidebar.warning(
    "Loading a dataset resets the current database."
)

if st.sidebar.button(
    "Load Dataset",
    use_container_width=True
):

    try:

        with st.spinner("Loading dataset..."):

            load_scale(
                dataset_size,
                with_indexes=with_indexes
            )

        st.session_state["loaded_size"] = dataset_size
        st.session_state["loaded_indexes"] = with_indexes
        st.session_state["purchase_position"] = 0

        st.session_state.pop("last_purchase", None)

        st.sidebar.success("Dataset loaded successfully!")

    except Exception as error:

        st.session_state.pop("loaded_size", None)
        st.session_state.pop("loaded_indexes", None)

        st.sidebar.error(str(error))


if "loaded_size" not in st.session_state:

    st.info(
        "Select a dataset size and load the database "
        "using the sidebar."
    )

    st.stop()


loaded_size = st.session_state["loaded_size"]
loaded_indexes = st.session_state["loaded_indexes"]

st.sidebar.divider()

st.sidebar.write("**Active configuration**")
st.sidebar.write(f"Dataset: {loaded_size:,} products")
st.sidebar.write(
    f"Secondary index: "
    f"{'Enabled' if loaded_indexes else 'Disabled'}"
)

statistics, _ = execute_operation(
    get_database_statistics
)

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Products",
    f"{statistics['products']:,}"
)

col2.metric(
    "Users",
    f"{statistics['users']:,}"
)

col3.metric(
    "Total sales score",
    f"{statistics['total_sales']:,}"
)

col4.metric(
    "Simulated purchases",
    f"{statistics['purchases']:,}"
)

st.divider()


tab_leaderboard, tab_rank, tab_purchase, tab_performance = st.tabs([
    "Leaderboard",
    "Rank Lookup",
    "Purchase Simulation",
    "Performance Analysis"
])

with tab_leaderboard:

    st.header("Best-Selling Products")

    k = st.selectbox(
        "Number of products",
        options=[10, 20, 50, 100],
        format_func=lambda value: f"Top {value}"
    )

    results, latency = execute_operation(
        get_top_k,
        k
    )

    leaderboard = pd.DataFrame(
        results,
        columns=[
            "Product ID",
            "Product Name",
            "Sales Count"
        ]
    )

    leaderboard.insert(
        0,
        "Rank",
        range(1, len(leaderboard) + 1)
    )

    st.metric(
        "Query latency",
        f"{latency:.3f} ms"
    )

    st.dataframe(
        leaderboard,
        hide_index=True,
        use_container_width=True
    )

    st.subheader("Top 10 Products by Sales")

    chart_data = leaderboard.head(10).copy()

    chart_data["Product"] = (
        chart_data["Product Name"]
        + " ("
        + chart_data["Product ID"].astype(str)
        + ")"
    )

    st.bar_chart(
        chart_data.set_index("Product")["Sales Count"]
    )

with tab_rank:

    st.header("Product Rank Lookup")

    st.write(
        "Find the current position of a product "
        "in the global sales leaderboard."
    )

    with st.form("rank_lookup_form"):

        product_id = st.number_input(
            "Product ID",
            min_value=1,
            value=1801690,
            step=1
        )

        search = st.form_submit_button(
            "Find Product Rank"
        )

    if search:

        product, _ = execute_operation(
            get_product,
            int(product_id)
        )

        if product is None:

            st.warning("Product not found.")

        else:

            rank, latency = execute_operation(
                get_rank,
                int(product_id)
            )

            display_product(product)

            st.divider()

            col1, col2 = st.columns(2)

            col1.metric(
                "Leaderboard rank",
                f"#{rank:,}"
            )

            col2.metric(
                "Query latency",
                f"{latency:.3f} ms"
            )

with tab_purchase:

    st.header("Purchase Simulation")

    st.write(
        "Replay purchase events and observe "
        "real-time leaderboard updates."
    )

    purchase_stream = load_purchase_stream(
        loaded_size
    )

    position = st.session_state.get(
        "purchase_position",
        0
    )

    st.progress(
        position / len(purchase_stream)
    )

    st.caption(
        f"Processed purchases: "
        f"{position:,} / {len(purchase_stream):,}"
    )

    if position < len(purchase_stream):

        purchase = purchase_stream.iloc[position]

        user_id = int(purchase["user_id"])
        product_id = int(purchase["product_id"])
        price = Decimal(str(purchase["price"]))

        product, _ = execute_operation(
            get_product,
            product_id
        )

        st.subheader("Next Purchase Event")

        col1, col2, col3 = st.columns(3)

        col1.metric("User ID", str(user_id))
        col2.metric("Product ID", str(product_id))
        col3.metric("Purchase price", f"{price:.2f}")

        if product is not None:

            st.write(f"**Product:** {product[1]}")
            st.write(f"**Current score:** {product[5]:,}")

        if st.button("Simulate Next Purchase"):

            try:

                before, _ = execute_operation(
                    get_product,
                    product_id
                )

                rank_before, _ = execute_operation(
                    get_rank,
                    product_id
                )

                _, latency = execute_operation(
                    record_purchase,
                    user_id,
                    product_id,
                    price,
                    datetime.now(timezone.utc)
                )

                after, _ = execute_operation(
                    get_product,
                    product_id
                )

                rank_after, _ = execute_operation(
                    get_rank,
                    product_id
                )

                st.session_state["last_purchase"] = {
                    "product_name": after[1],
                    "score_before": before[5],
                    "score_after": after[5],
                    "rank_before": rank_before,
                    "rank_after": rank_after,
                    "latency": latency
                }

                st.session_state["purchase_position"] += 1

                st.rerun()

            except Exception as error:

                st.error(str(error))

    else:

        st.info("All purchase events have been processed.")


    if "last_purchase" in st.session_state:

        result = st.session_state["last_purchase"]

        st.divider()

        st.success("Purchase recorded successfully!")

        st.subheader(result["product_name"])

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Updated sales score",
            f"{result['score_after']:,}",
            delta=(
                result["score_after"]
                - result["score_before"]
            )
        )

        col2.metric(
            "Updated rank",
            f"#{result['rank_after']:,}",
            delta=(
                result["rank_before"]
                - result["rank_after"]
            )
        )

        col3.metric(
            "Transaction latency",
            f"{result['latency']:.3f} ms"
        )

        st.caption(
            f"Previous rank: #{result['rank_before']:,}"
        )

with tab_performance:

    st.header("PostgreSQL Performance Analysis")

    benchmark_path = (
        RESULTS_DIR / "sql_benchmark_rounds.csv"
    )

    if not benchmark_path.exists():

        st.warning("Benchmark results not found.")

    else:

        benchmark = pd.read_csv(benchmark_path)

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Benchmark rounds",
            benchmark["round"].nunique()
        )

        col2.metric(
            "Dataset sizes",
            benchmark["dataset_size"].nunique()
        )

        col3.metric(
            "Measured operations",
            f"{benchmark['operations'].sum():,}"
        )

        st.divider()

        operation_labels = {
            "top_k": "Top-K Retrieval",
            "rank_lookup": "Rank Lookup",
            "score_update": "Score Update"
        }

        selected_operation = st.selectbox(
            "Operation",
            options=list(operation_labels.keys()),
            format_func=lambda value: operation_labels[value]
        )

        metric_labels = {
            "mean_ms": "Average latency (ms)",
            "p95_ms": "P95 latency (ms)",
            "throughput_ops_sec": "Throughput (operations/s)"
        }

        selected_metric = st.selectbox(
            "Performance metric",
            options=list(metric_labels.keys()),
            format_func=lambda value: metric_labels[value]
        )

        filtered = benchmark[
            benchmark["operation"] == selected_operation
        ].copy()

        filtered["Configuration"] = filtered[
            "with_indexes"
        ].map({
            False: "Without secondary index",
            True: "With secondary index"
        })

        aggregated = (
            filtered.groupby(
                ["dataset_size", "Configuration"]
            )[selected_metric]
            .agg(["mean", "std"])
            .reset_index()
        )

        chart_data = aggregated.pivot(
            index="dataset_size",
            columns="Configuration",
            values="mean"
        )

        chart_data = chart_data.sort_index()

        chart_data.index = [
            f"{size // 1000}k"
            for size in chart_data.index
        ]

        st.subheader(
            operation_labels[selected_operation]
        )

        st.caption(
            metric_labels[selected_metric]
        )

        st.line_chart(
            chart_data,
            color=["#9674CB", "#9B9BA8"]
        )

        st.subheader("Aggregated Results")

        st.dataframe(
            aggregated.rename(columns={
                "dataset_size": "Dataset size",
                "mean": "Mean",
                "std": "Standard deviation"
            }).round(4),
            hide_index=True,
            use_container_width=True
        )

        st.caption(
            "Statistics aggregated across benchmark rounds."
        )

        with st.expander("View raw benchmark results"):

            st.dataframe(
                filtered,
                hide_index=True,
                use_container_width=True
            )

        st.download_button(
            label="Download Benchmark Results",
            data=benchmark.to_csv(index=False),
            file_name="sql_benchmark_rounds.csv",
            mime="text/csv"
        )
