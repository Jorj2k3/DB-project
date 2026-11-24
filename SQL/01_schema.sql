DROP TABLE IF EXISTS purchases;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    total_spent NUMERIC(12, 2) NOT NULL DEFAULT 0.00
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    brand VARCHAR(100),
    price NUMERIC(10, 2) NOT NULL,
    sales_count INT NOT NULL DEFAULT 0
);

CREATE TABLE purchases (
    purchase_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    price_paid NUMERIC(10, 2) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);