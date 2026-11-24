import os
import time
from pathlib import Path
import psycopg2

SQL_DIR = Path(__file__).resolve().parent

VALID_SIZES = [1000, 10000, 100000]


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

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)

        print(f"[SQL] Executed {filename}")

    finally:
        conn.close()


def load_scale(size: int, with_indexes: bool = False):

    if size not in VALID_SIZES:
        raise ValueError(f"Invalid dataset size: {size}")

    # 1. Reset database schema

    run_sql_file("01_schema.sql")

    conn = get_pg_conn()
    start = time.perf_counter()

    try:
        with conn:
            with conn.cursor() as cur:

                # 2. Create temporary staging table

                cur.execute("""
                    CREATE TEMP TABLE staging_products (
                        product_id BIGINT,
                        product_name VARCHAR(255),
                        category VARCHAR(255),
                        brand VARCHAR(100),
                        price NUMERIC(10, 2),
                        sales_count INT
                    ) ON COMMIT DROP;
                """)

                # 3. Import products CSV into staging table

                cur.execute(f"""
                    COPY staging_products (
                        product_id,
                        product_name,
                        category,
                        brand,
                        price,
                        sales_count
                    )
                    FROM '/data/products_{size}.csv'
                    DELIMITER ',' CSV HEADER;
                """)

                # 4. Populate categories

                cur.execute("""
                    INSERT INTO categories (category_name)
                    SELECT DISTINCT category
                    FROM staging_products;
                """)

                # 5. Populate brands

                cur.execute("""
                    INSERT INTO brands (brand_name)
                    SELECT DISTINCT brand
                    FROM staging_products;
                """)

                # 6. Populate products

                cur.execute("""
                    INSERT INTO products (
                        product_id,
                        product_name,
                        category_id,
                        brand_id,
                        price,
                        sales_count
                    )
                    SELECT
                        sp.product_id,
                        sp.product_name,
                        c.category_id,
                        b.brand_id,
                        sp.price,
                        sp.sales_count
                    FROM staging_products sp
                    JOIN categories c
                        ON sp.category = c.category_name
                    JOIN brands b
                        ON sp.brand = b.brand_name;
                """)

                # 7. Populate users

                cur.execute(f"""
                    COPY users (user_id, total_spent)
                    FROM '/data/users_{size}.csv'
                    DELIMITER ',' CSV HEADER;
                """)

                # 8. Validate row counts

                cur.execute("SELECT COUNT(*) FROM products;")
                product_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM users;")
                user_count = cur.fetchone()[0]

                if product_count != size or user_count != size:
                    raise ValueError(
                        f"Invalid row counts: "
                        f"{product_count} products, "
                        f"{user_count} users"
                    )

                # 9. Update PostgreSQL statistics

                cur.execute("ANALYZE;")

        elapsed = time.perf_counter() - start

        print(
            f"[SQL] Loaded {product_count:,} products "
            f"& {user_count:,} users in {elapsed:.2f}s"
        )

    finally:
        conn.close()

    # 10. Create optional secondary indexes

    if with_indexes:
        run_sql_file("02_indexes.sql")


if __name__ == "__main__":
    load_scale(1000, with_indexes=False)