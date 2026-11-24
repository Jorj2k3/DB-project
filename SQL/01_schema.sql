-- Drop existing tables in dependency order
DROP TABLE IF EXISTS purchases;

DROP TABLE IF EXISTS products;

DROP TABLE IF EXISTS users;

DROP TABLE IF EXISTS categories;

DROP TABLE IF EXISTS brands;

-- 1. Categories
CREATE TABLE categories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(255) NOT NULL UNIQUE
);

-- 2. Brands
CREATE TABLE brands (
    brand_id SERIAL PRIMARY KEY,
    brand_name VARCHAR(100) NOT NULL UNIQUE
);

-- 3. Users
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    total_spent NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    CHECK (total_spent >= 0)
);

-- 4. Products
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category_id INT NOT NULL REFERENCES categories(category_id),
    brand_id INT NOT NULL REFERENCES brands(brand_id),
    price NUMERIC(10, 2) NOT NULL,
    sales_count INT NOT NULL DEFAULT 0,
    CHECK (price >= 0),
    CHECK (sales_count >= 0)
);

-- 5. Purchases
CREATE TABLE purchases (
    purchase_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    price_paid NUMERIC(10, 2) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (price_paid >= 0)
);