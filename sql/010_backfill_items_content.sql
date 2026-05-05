-- ============================================================
-- 阶段 2 Step 2.2: 迁移历史数据到 items_content
-- body_text → raw_body（enriched_body 保持 NULL）
-- ============================================================

BEGIN;

-- 有 body_text 的记录：填 raw_body
INSERT INTO items_content (item_id, raw_body)
SELECT id, body_text FROM raw_items
WHERE body_text IS NOT NULL
ON CONFLICT (item_id) DO NOTHING;

-- body_text IS NULL 的也插入空记录保持 1:1
INSERT INTO items_content (item_id)
SELECT id FROM raw_items
WHERE id NOT IN (SELECT item_id FROM items_content)
ON CONFLICT (item_id) DO NOTHING;

-- 验证行数一致
DO $$
DECLARE r_count INT; c_count INT;
BEGIN
    SELECT count(*) INTO r_count FROM raw_items;
    SELECT count(*) INTO c_count FROM items_content;
    IF r_count != c_count THEN
        RAISE EXCEPTION 'count mismatch: raw_items=%, items_content=%', r_count, c_count;
    END IF;
END $$;

COMMIT;
