def record_purchase(
    conn,
    user_id,
    product_id,
    price,
    event_time
):
    with conn:
        with conn.cursor() as cur:

            # 1. Record the purchase
            cur.execute("""
                INSERT INTO purchases (
                    user_id,
                    product_id,
                    price_paid,
                    event_time
                )
                VALUES (%s, %s, %s, %s);
            """, (user_id, product_id, price, event_time))

            # 2. Update product leaderboard score
            cur.execute("""
                UPDATE products
                SET sales_count = sales_count + 1
                WHERE product_id = %s;
            """, (product_id,))

            # 3. Update user total spending
            cur.execute("""
                UPDATE users
                SET total_spent = total_spent + %s
                WHERE user_id = %s;
            """, (price, user_id))


def get_top_k(conn, k=10):

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    product_id,
                    product_name,
                    sales_count
                FROM products
                ORDER BY sales_count DESC, product_id DESC
                LIMIT %s;
            """, (k,))

            return cur.fetchall()
        
def get_rank(conn, product_id):

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT 1 + (
                    SELECT COUNT(*)
                    FROM products p
                    WHERE
                        p.sales_count > target.sales_count
                        OR (
                            p.sales_count = target.sales_count
                            AND p.product_id > target.product_id
                        )
                ) AS rank
                FROM products target
                WHERE target.product_id = %s;
            """, (product_id,))

            result = cur.fetchone()

            return result[0] if result else None
        
def increment_score(conn, product_id):
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET sales_count = sales_count + 1
                WHERE product_id = %s;
            """, (product_id,))

def get_product(conn, product_id):

    with conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    p.product_id,
                    p.product_name,
                    c.category_name,
                    b.brand_name,
                    p.price,
                    p.sales_count
                FROM products p
                JOIN categories c
                    ON p.category_id = c.category_id
                JOIN brands b
                    ON p.brand_id = b.brand_id
                WHERE p.product_id = %s;
            """, (product_id,))

            return cur.fetchone()