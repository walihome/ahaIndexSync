-- ============================================================
-- 阶段 6: raw_items 删冗余列（不可逆）
-- 前置条件：阶段 3-5 稳定运行至少两周
--           grep 确认无代码读 raw_items.body_text / content_source / content_quality
-- ============================================================

BEGIN;

-- 1. 备份（防御性，保留 30 天后 DROP）
CREATE TABLE raw_items_body_backup_202605 AS
SELECT id, body_text, content_source, content_quality, updated_at AS backup_at
FROM raw_items
WHERE body_text IS NOT NULL;

-- 2. 删冗余列
ALTER TABLE raw_items
    DROP COLUMN body_text,
    DROP COLUMN content_source,
    DROP COLUMN content_quality;

-- 3. 删无意义默认值（这些默认值在重构后语义不正确）
ALTER TABLE raw_items
    ALTER COLUMN source_name DROP DEFAULT,
    ALTER COLUMN source_type DROP DEFAULT,
    ALTER COLUMN content_type DROP DEFAULT;

COMMIT;

-- 备份表保留 30 天后手动执行：
-- DROP TABLE raw_items_body_backup_202605;
