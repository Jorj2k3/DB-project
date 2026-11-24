CREATE INDEX IF NOT EXISTS idx_products_leaderboard ON products (sales_count DESC, product_id DESC);

ANALYZE products;