-- ============================================================
-- 阶段 2 Step 2.1: 建 items_content 表 + items_content_test
-- items_content 与 raw_items 1:1 关联，存储内容层数据
-- ============================================================

BEGIN;

-- items_content 主表
CREATE TABLE IF NOT EXISTS items_content (
    item_id             TEXT PRIMARY KEY
                        REFERENCES raw_items(id) ON DELETE CASCADE,
    raw_body            TEXT,
    -- scraper 抓到的原始内容（RSS 摘要 / API 描述 / Twitter 正文）
    -- scraper 写入后不可变

    enriched_body       TEXT,
    -- 全文抓取产物（Jina / trafilatura）
    -- 未抓取或失败时为 NULL

    enriched_source     TEXT,
    -- 'jina' / 'trafilatura' / NULL（未抓取）

    enriched_quality    REAL,
    -- 0.0-1.0，未评估时为 NULL

    enriched_at         TIMESTAMPTZ,
    -- 全文抓取完成时间

    fetch_attempts      INT NOT NULL DEFAULT 0,
    -- 全文抓取尝试次数（含失败）

    last_fetch_error    TEXT,
    -- 最近一次抓取失败的错误信息（截断到 500 字）

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_enriched_source CHECK (
        enriched_source IS NULL
        OR enriched_source IN ('jina', 'trafilatura')
    ),
    CONSTRAINT chk_enriched_quality CHECK (
        enriched_quality IS NULL
        OR (enriched_quality >= 0.0 AND enriched_quality <= 1.0)
    )
);

-- fetch_content stage 选待处理项的高效路径
CREATE INDEX IF NOT EXISTS idx_items_content_pending
    ON items_content(item_id)
    WHERE enriched_body IS NULL AND fetch_attempts < 3;

CREATE INDEX IF NOT EXISTS idx_items_content_enriched_source
    ON items_content(enriched_source)
    WHERE enriched_source IS NOT NULL;

-- updated_at 触发器（复用已有的 update_updated_at_column 函数）
CREATE TRIGGER trigger_update_items_content_updated_at
    BEFORE UPDATE ON items_content
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE items_content IS
    '内容层：与 raw_items 1:1 关联。
     raw_body 来自 scraper（不可变），enriched_body 来自全文抓取（可重试）。
     下游取内容用 COALESCE(enriched_body, raw_body)。';

COMMENT ON COLUMN items_content.raw_body IS
    'Scraper 抓到的原始内容。一旦写入不再修改。';

COMMENT ON COLUMN items_content.enriched_body IS
    '全文抓取产物。NULL 表示尚未抓取或抓取失败。';

-- items_content_test 测试表
CREATE TABLE IF NOT EXISTS items_content_test (
    LIKE items_content INCLUDING ALL,
    CONSTRAINT items_content_test_item_id_fkey
        FOREIGN KEY (item_id) REFERENCES raw_items_test(id) ON DELETE CASCADE
);

CREATE TRIGGER trigger_update_items_content_test_updated_at
    BEFORE UPDATE ON items_content_test
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE items_content_test IS 'items_content 的测试隔离表';

-- fetch_attempts 原子递增函数（供 fetch_content stage 调用）
CREATE OR REPLACE FUNCTION increment_fetch_attempts(p_item_id TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE items_content
    SET fetch_attempts = fetch_attempts + 1
    WHERE item_id = p_item_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION increment_fetch_attempts IS
    'fetch_content stage 调用：原子递增 fetch_attempts 计数器';

COMMIT;
