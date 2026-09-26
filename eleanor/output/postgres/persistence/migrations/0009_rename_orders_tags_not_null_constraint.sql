-- 0002_rename_tag_to_tags.sql did not rename the orders_tag_not_null constraint
-- to orders_tags_not_null under PG18

ALTER TABLE orders ALTER COLUMN tags DROP NOT NULL;
ALTER TABLE orders ALTER COLUMN tags SET NOT NULL;
