-- ============================================================
-- 阶段 5: raw_items 加 snapshot_date / scraper_slug / scraper_config_snapshot
-- ============================================================

BEGIN;

-- 1. 加列（先允许 NULL）
ALTER TABLE raw_items
    ADD COLUMN snapshot_date DATE,
    ADD COLUMN scraper_slug TEXT,
    ADD COLUMN scraper_config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 2. 回填 snapshot_date：created_at 转北京时间的日期
UPDATE raw_items
SET snapshot_date = (created_at AT TIME ZONE 'Asia/Shanghai')::date
WHERE snapshot_date IS NULL;

-- 3. 回填 scraper_slug：source_name 匹配 scraper_configs.name
UPDATE raw_items r
SET scraper_slug = sc.slug
FROM scraper_configs sc
WHERE r.source_name = sc.name
  AND r.scraper_slug IS NULL;

-- 3b. 手动映射历史遗留的 source_name（scraper_configs 中已不存在的名称）
-- "GitHub"（34 条，2026-03-06 ~ 03-14）→ 早期 GitHub Trending 配置名
UPDATE raw_items SET scraper_slug = 'github-trending'
WHERE source_name = 'GitHub' AND scraper_slug IS NULL;

-- "Meta AI Blog"（11 条，2026-03-10 ~ 03-12）→ 已下线的 scraper，映射到同类型 Blog
UPDATE raw_items SET scraper_slug = 'mistral-ai-blog'
WHERE source_name = 'Meta AI Blog' AND scraper_slug IS NULL;

-- 4. 对账：检查未匹配的
DO $$
DECLARE null_count INT;
BEGIN
    SELECT count(*) INTO null_count FROM raw_items
    WHERE scraper_slug IS NULL OR snapshot_date IS NULL;
    IF null_count > 0 THEN
        RAISE WARNING '% rows have NULL scraper_slug or snapshot_date, please backfill manually', null_count;
    END IF;
END $$;

-- 5. 加 NOT NULL（如果有 NULL 数据，需先手动修复后再执行）
-- 注意：如果上面 RAISE WARNING 了，需要先手动处理 NULL 数据
-- ALTER TABLE raw_items
--     ALTER COLUMN snapshot_date SET NOT NULL,
--     ALTER COLUMN scraper_slug SET NOT NULL;

-- 6. 加索引
CREATE INDEX IF NOT EXISTS idx_raw_items_snapshot_date ON raw_items(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_items_source_snapshot ON raw_items(source_name, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_items_scraper_slug ON raw_items(scraper_slug);

-- 7. 注释
COMMENT ON COLUMN raw_items.snapshot_date IS
    '业务归属日期（北京时间）：这条数据归属于哪一期日报。
     由 pipeline runner 启动时计算或通过参数显式指定。
     ≠ created_at（DB 写入时间）≠ published_at（原文发布时间）';

COMMENT ON COLUMN raw_items.scraper_slug IS
    'FK 到 scraper_configs.slug。slug 是稳定业务键，scraper 配置重建后值不变。';

COMMENT ON COLUMN raw_items.scraper_config_snapshot IS
    '抓取当时的 scraper_configs.config 完整快照。
     用于回答"这条历史数据是用什么参数抓出来的"。
     scraper_configs.config 是可变状态，此字段是不可变快照，二者会脱节，这是设计意图。';

COMMIT;
