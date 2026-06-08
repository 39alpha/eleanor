ALTER TABLE "orders" RENAME "tag" to "tags";

ALTER TABLE "orders" ALTER COLUMN "tags" DROP DEFAULT;
ALTER TABLE "orders" ALTER COLUMN "tags" TYPE TEXT[] USING
  CASE WHEN "tags" = '' THEN
    ARRAY[]::TEXT[]
  ELSE
    ARRAY["tags"]
  END;
ALTER TABLE "orders" ALTER COLUMN "tags" SET DEFAULT '{}';

DROP INDEX IF EXISTS "orders_tag_idx";
CREATE INDEX "orders_tags_idx" ON "orders" USING GIN ("tags");
