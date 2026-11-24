import time
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import streamlit as st
from SQL.sql_loader import get_pg_conn, load_scale as load_sql
from NoSQL.redis_loader import get_redis_client, load_scale as load_redis
from SQL import leaderboard as sql
from NoSQL import leaderboard as nosql

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
RESULTS = ROOT / 'results'
st.set_page_config(page_title='Online Shop', layout='wide')


def timed(fn, client, *args):
    start = time.perf_counter_ns()
    result = fn(client, *args)
    return result, (time.perf_counter_ns() - start) / 1e6


def compare(pg_fn, redis_fn, *args):
    conn = get_pg_conn()
    try:
        r = get_redis_client()
        try:
            r.ping()  # Establish Redis connection outside measured interval.
            return timed(pg_fn, conn, *args), timed(redis_fn, r, *args)
        finally:
            r.close()
    finally:
        conn.close()


@st.cache_data
def read_data(size, kind):
    return pd.read_csv(DATA / f'{kind}_{size}.csv')


def show_comparison(results, table=False):
    for col, name, (value, ms) in zip(st.columns(2), ['PostgreSQL', 'Redis'], results):
        with col:
            st.subheader(name)
            st.metric('Live latency', f'{ms:.3f} ms')
            if table:
                frame = pd.DataFrame(value, columns=['Product ID', 'Product name', 'Sales'])
                frame.insert(0, 'Rank', range(1, len(frame)+1))
                st.dataframe(frame, hide_index=True, use_container_width=True)
            else:
                st.metric('Rank', str(value) if value is not None else 'Not found')
    if results[0][0] == results[1][0]:
        st.success('Results match.')
    else:
        st.warning('Results differ. Check scores and numeric vs lexicographic tie-breaking.')
    st.caption('Single client-side measurement; not a statistical benchmark.')


TOP_SQL = '''SELECT product_id, product_name, sales_count
FROM products
ORDER BY sales_count DESC, product_id DESC
LIMIT %s'''
RANK_SQL = '''SELECT 1 + (
    SELECT COUNT(*) FROM products p
    WHERE p.sales_count > target.sales_count
       OR (p.sales_count = target.sales_count
           AND p.product_id > target.product_id)
) AS rank
FROM products target WHERE target.product_id = %s'''

st.sidebar.title('Database configuration')
size = st.sidebar.selectbox('Dataset size', [1000, 10000, 100000], format_func=lambda n: f'{n:,}')
indexed = st.sidebar.checkbox('PostgreSQL secondary index', value=True)
if st.sidebar.button('Initialize databases'):
    st.session_state.pop('loaded', None)
    st.session_state.pop('last_purchase', None)
    st.session_state.pop('inconsistent', None)
    try:
        with st.spinner('Loading identical datasets...'):
            load_sql(size, indexed)
            load_redis(size)
        st.session_state.loaded = (size, indexed)
        st.session_state.purchase_count = 0
        st.sidebar.success('Both databases initialized.')
    except Exception as exc:
        st.error(f'Initialization failed: {exc}')

page = st.sidebar.radio('Navigation', ['Shop', 'Live Leaderboard', 'Rank Lookup', 'Query Playground', 'Performance Analysis'])
st.title('Online Shop | Database Comparison')
st.caption('PostgreSQL & Redis — independent implementations of the same workload')

if page == 'Performance Analysis':
    st.header('Experimental results')
    frames = []
    for filename, database in [('sql_benchmark_rounds.csv', 'PostgreSQL'), ('redis_benchmark_rounds.csv', 'Redis')]:
        path = RESULTS / filename
        if path.exists():
            df = pd.read_csv(path)
            df['series'] = database if database == 'Redis' else df['with_indexes'].astype(str).str.lower().map({'true':'PostgreSQL with index','false':'PostgreSQL without index'})
            frames.append(df)
        else:
            st.warning(f'Missing {filename}')
    if frames:
        df = pd.concat(frames, ignore_index=True)
        st.metric('Recorded measurements', f"{df['operations'].sum():,}")
        op = st.selectbox('Operation', ['top_k','rank_lookup','score_update'])
        metric = st.selectbox('Metric', ['mean_ms','p95_ms','throughput_ops_sec'], format_func=lambda x: {'mean_ms':'Average latency (ms)','p95_ms':'Mean round P95 (ms)','throughput_ops_sec':'Throughput (ops/s)'}[x])
        summary = df[df.operation == op].groupby(['dataset_size','series'])[metric].agg(['mean','std','count']).reset_index()
        st.line_chart(summary.pivot(index='dataset_size', columns='series', values='mean').sort_index())
        st.dataframe(summary, hide_index=True)
        suffix = {'mean_ms':'mean_latency','p95_ms':'p95_latency','throughput_ops_sec':'throughput'}[metric]
        plot = RESULTS / 'comparison_plots' / f'{op}_{suffix}.png'
        if plot.exists():
            st.image(str(plot), caption='Saved comparison plot')
        st.caption('Mean and standard deviation across recorded rounds. P95 is averaged across rounds, not pooled.')
    st.stop()

if 'loaded' not in st.session_state:
    st.info('Initialize both databases using the sidebar to start the demo.')
    st.stop()
active_size, active_index = st.session_state.loaded
st.sidebar.info(f'Active: {active_size:,} products | Secondary index: {active_index}')
if (size, indexed) != (active_size, active_index):
    st.sidebar.warning('Selection not applied. Initialize to change configuration.')
if st.session_state.get('inconsistent'):
    st.error('A purchase may have been applied to only one database. Reinitialize before continuing.')
    st.stop()

products = read_data(active_size, 'products')
users = read_data(active_size, 'users')


def select_product(key):
    pid = st.number_input('Product ID', min_value=1, value=int(products.iloc[0].product_id), step=1, key=key)
    return int(pid)


try:
    if page == 'Shop':
        st.header('Product catalog')
        a,b,c = st.columns(3)
        a.metric('Products', f'{active_size:,}')
        b.metric('Users', f'{len(users):,}')
        c.metric('Demo purchases', st.session_state.purchase_count)
        category = st.selectbox('Category', ['All categories'] + sorted(products.category.dropna().unique().tolist()))
        search = st.text_input('Search product name or ID')
        catalog = products if category == 'All categories' else products[products.category == category]
        if search:
            catalog = catalog[catalog.product_name.str.contains(search, case=False, regex=False, na=False) | catalog.product_id.astype(str).str.contains(search, regex=False)]
        catalog = catalog.sort_values(['sales_count','product_id'], ascending=False)
        st.caption(f'{len(catalog):,} matching products; catalog ordered by initial sales.')
        uid = int(st.number_input('Customer ID', min_value=1, value=int(users.iloc[0].user_id), step=1))
        cols = st.columns(3)
        for i, row in enumerate(catalog.head(9).itertuples()):
            pid = int(row.product_id)
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f'**{row.product_name}**')
                    st.caption(f'{row.brand} | {row.category} | ID {pid}')
                    st.metric('Price (dataset units)', f'{row.price:.2f}')
                    if st.button('Buy now', key=f'buy_{pid}', use_container_width=True):
                        if uid not in set(users.user_id):
                            st.error('Customer ID does not exist.')
                        else:
                            before = compare(sql.get_product, nosql.get_product, pid)
                            ranks_before = compare(sql.get_rank, nosql.get_rank, pid)
                            try:
                                writes = compare(sql.record_purchase, nosql.record_purchase, uid, pid, Decimal(str(row.price)), datetime.now(timezone.utc))
                                after = compare(sql.get_product, nosql.get_product, pid)
                                ranks_after = compare(sql.get_rank, nosql.get_rank, pid)
                                st.session_state.last_purchase = (pid, before, after, ranks_before, ranks_after, writes)
                                st.session_state.purchase_count += 1
                            except Exception:
                                st.session_state.inconsistent = True
                                raise
                            st.rerun()
        if 'last_purchase' in st.session_state:
            pid, before, after, rb, ra, writes = st.session_state.last_purchase
            st.subheader(f'Last purchase — product {pid}')
            for i, col in enumerate(st.columns(2)):
                with col:
                    st.markdown(f"**{['PostgreSQL','Redis'][i]}**")
                    st.metric('Sales', after[i][0][5], int(after[i][0][5])-int(before[i][0][5]))
                    st.metric('Rank', ra[i][0], rb[i][0]-ra[i][0])
                    st.metric('Full purchase latency', f'{writes[i][1]:.3f} ms')
            if after[0][0][5] != after[1][0][5]:
                st.error('Product scores differ.')
            elif ra[0][0] != ra[1][0]:
                st.warning('Scores match but ranks differ; check tie-breaking.')
            else:
                st.success('Product score and rank match.')
            st.caption('Full purchase operations differ in scope from the score-update microbenchmark.')
    elif page == 'Live Leaderboard':
        st.header('Live leaderboard')
        k = st.selectbox('Top K', [10,20,50,100])
        if st.button('Retrieve leaderboard'):
            show_comparison(compare(sql.get_top_k, nosql.get_top_k, k), table=True)
    elif page == 'Rank Lookup':
        st.header('Exact product rank')
        pid = select_product('rank_id')
        if st.button('Find rank'):
            show_comparison(compare(sql.get_rank, nosql.get_rank, pid))
        st.markdown('PostgreSQL counts preceding rows; Redis uses an ordered Sorted Set with rank support.')
    elif page == 'Query Playground':
        st.header('Query playground')
        choice = st.radio('Query', ['Top-K products','Exact product rank'])
        top = choice == 'Top-K products'
        arg = st.selectbox('K', [10,20,50,100], key='query_k') if top else select_product('query_id')
        query = TOP_SQL if top else RANK_SQL
        left,right = st.columns(2)
        with left:
            st.subheader('PostgreSQL')
            st.code(query.replace('%s', str(arg)), language='sql')
        with right:
            st.subheader('Redis')
            st.code(f'ZRANGE leaderboard:products 0 {arg-1} REV WITHSCORES\n# HGET product:<id> name (pipeline)' if top else f'ZREVRANK leaderboard:products {arg}\n# Add 1 to obtain application rank', language='text')
        if st.button('Execute both queries'):
            show_comparison(compare(sql.get_top_k if top else sql.get_rank, nosql.get_top_k if top else nosql.get_rank, arg), table=top)
except Exception as exc:
    st.error(f'Operation failed: {exc}')
    if st.session_state.get('inconsistent'):
        st.warning('Do not retry the purchase. Reinitialize both databases first.')
