import os
import time
from pathlib import Path
import psycopg2

SQL_DIR = Path(__file__).resolve().parent

def get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5433)),
        dbname=os.getenv("PG_DB", "shop_db"),
        user=os.getenv("PG_USER", "shop_user"),
        password=os.getenv("PG_PASSWORD", "shop_password"),
    )

def run_sql_file(filename: str):
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    conn = get_pg_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.close()
    print(f"[SQL] Executed {filename}")

def load_scale(size: int, with_indexes: bool = False):
    run_sql_file("01_schema.sql")

    conn = get_pg_conn()
    conn.autocommit = True
    start = time.perf_counter()

    with conn.cursor() as cur:
        cur.execute(f"""
            COPY products(product_id, product_name, category, brand, price, sales_count)
            FROM '/data/products_{size}.csv'
            DELIMITER ',' CSV HEADER;
        """)
        cur.execute(f"""
            COPY users(user_id, total_spent)
            FROM '/data/users_{size}.csv'
            DELIMITER ',' CSV HEADER;
        """)

    conn.close()
    elapsed = time.perf_counter() - start
    print(f"[SQL] Loaded {size:,} products & {size:,} users in {elapsed:.2f}s")

    if with_indexes:
        run_sql_file("02_indexes.sql")

if __name__ == "__main__":
    load_scale(1000, with_indexes=False)