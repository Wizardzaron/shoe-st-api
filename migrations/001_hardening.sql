-- Back up your database and review this in staging before running it.
-- Any uniqueness violation stops the migration; resolve duplicates manually.
BEGIN;
ALTER TABLE customer ALTER COLUMN passwd TYPE TEXT;
ALTER TABLE customer ALTER COLUMN temporarypasscode TYPE TEXT USING temporarypasscode::text;
-- Invalidate the previous insecure numeric recovery codes.
UPDATE customer SET temporarypasscode = NULL, codedate = NULL;
ALTER TABLE customer ADD COLUMN IF NOT EXISTS reset_token_digest TEXT;
ALTER TABLE customer ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS customer_username_unique ON customer(username);
CREATE UNIQUE INDEX IF NOT EXISTS customer_email_unique ON customer(email);
CREATE UNIQUE INDEX IF NOT EXISTS cart_customer_unique ON cart(customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS cartitems_shoe_cart_size_unique ON cartitems(shoe_id,cart_id,size_id);
CREATE UNIQUE INDEX IF NOT EXISTS image_one_main_per_shoe ON image(shoe_id) WHERE main_image = 1;
ALTER TABLE cartitems ADD CONSTRAINT cartitems_quantity_positive CHECK (quantity BETWEEN 1 AND 99);
ALTER TABLE sizes ADD CONSTRAINT sizes_stock_nonnegative CHECK (in_stock >= 0);
COMMIT;
