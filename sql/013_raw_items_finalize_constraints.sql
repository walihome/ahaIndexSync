-- ============================================================
-- 阶段 7: 加 FK + 删 UNIQUE(original_url)
-- 前置条件：阶段 5 的 snapshot_date / scraper_slug 已 NOT NULL
--           （需要先执行 011 中被注释掉的 NOT NULL 语句）
-- ============================================================

BEGIN;

-- 1. 加 FK（scraper_slug → scraper_configs.slug）
ALTER TABLE raw_items
    ADD CONSTRAINT raw_items_scraper_slug_fkey
    FOREIGN KEY (scraper_slug) REFERENCES scraper_configs(slug);

-- 2. 删 UNIQUE(original_url)（PK 已通过 md5(url) 保证唯一）
ALTER TABLE raw_items
    DROP CONSTRAINT raw_items_original_url_key;

COMMIT;
