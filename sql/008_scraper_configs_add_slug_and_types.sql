-- ============================================================
-- 阶段 1: scraper_configs 加 slug + source_type + content_type
-- 从 config JSONB 提取 source_type / content_type 到顶层列
-- ============================================================

BEGIN;

-- 1. 加列
ALTER TABLE scraper_configs ADD COLUMN slug TEXT;
ALTER TABLE scraper_configs ADD COLUMN source_type TEXT;
ALTER TABLE scraper_configs ADD COLUMN content_type TEXT;

-- 2. 从 config JSONB 提取 source_type / content_type
UPDATE scraper_configs
SET
    source_type = config->>'source_type',
    content_type = config->>'content_type';

-- 2b. 中文名手动映射 slug（正则无法处理非 ASCII）
UPDATE scraper_configs SET slug = 'sspai' WHERE name = '少数派';
UPDATE scraper_configs SET slug = '36kr' WHERE name = '36氪';
UPDATE scraper_configs SET slug = 'huxiu' WHERE name = '虎嗅';
UPDATE scraper_configs SET slug = 'solidot' WHERE name = '奇客Solidot';
UPDATE scraper_configs SET slug = 'ithome' WHERE name = 'IT之家';

-- 2c. 英文名自动生成 slug
UPDATE scraper_configs
SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'))
WHERE slug IS NULL;

-- 3. 检查 slug 唯一性
DO $$
DECLARE dup_count INT;
BEGIN
    SELECT count(*) INTO dup_count FROM (
        SELECT slug FROM scraper_configs GROUP BY slug HAVING count(*) > 1
    ) t;
    IF dup_count > 0 THEN
        RAISE EXCEPTION 'duplicate slugs detected, please resolve manually';
    END IF;
END $$;

-- 4. 检查 source_type / content_type 是否全部回填
DO $$
DECLARE null_count INT;
BEGIN
    SELECT count(*) INTO null_count FROM scraper_configs
    WHERE source_type IS NULL OR content_type IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION '% rows have NULL source_type or content_type in config JSONB', null_count;
    END IF;
END $$;

-- 5. 加约束
ALTER TABLE scraper_configs
    ALTER COLUMN slug SET NOT NULL,
    ADD CONSTRAINT scraper_configs_slug_key UNIQUE (slug),
    ALTER COLUMN source_type SET NOT NULL,
    ALTER COLUMN content_type SET NOT NULL;

-- 6. 从 config JSONB 中删除已提升的字段（避免双重来源）
UPDATE scraper_configs
SET config = config - 'source_type' - 'content_type';

-- 7. 添加注释
COMMENT ON COLUMN scraper_configs.slug IS
    '稳定业务键。scraper 配置重建后值不变（name 可能改）。raw_items.scraper_slug FK 关联此列。';
COMMENT ON COLUMN scraper_configs.source_type IS
    '数据源类型：REPO / BLOG / NEWS / TWEET / ARTICLE / PRODUCT';
COMMENT ON COLUMN scraper_configs.content_type IS
    '内容类型：repo / article / tweet / reddit / hf_papers / hf_model / product_hunt / v2ex_hot / linuxdo_hot';

COMMIT;
