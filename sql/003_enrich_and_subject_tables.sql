-- ============================================================
-- AhaIndexSync - 第二层内容增厚 + Subject 资产体系
-- 4 张新表：item_enrichments / subjects / subject_mentions / subject_aliases
--
-- 默认创建生产表（无后缀）。如需同时创建测试表（_test 后缀），
-- 执行完本文件后再执行 003_enrich_and_subject_tables_test.sql
-- ============================================================

-- 1. item_enrichments: 第二层增厚数据
CREATE TABLE IF NOT EXISTS item_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    enrichment_type TEXT NOT NULL,
    enricher_name TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_item_enrichments_key
    ON item_enrichments (item_id, snapshot_date, enrichment_type);
CREATE INDEX IF NOT EXISTS idx_item_enrichments_date
    ON item_enrichments (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_item_enrichments_type
    ON item_enrichments (enrichment_type, snapshot_date);

COMMENT ON TABLE item_enrichments IS '第二层增厚：社区反馈/竞品/历史关联等结构化补充数据';
COMMENT ON COLUMN item_enrichments.item_id IS '关联 raw_items.id（也是 processed_items.item_id），MD5 hex';
COMMENT ON COLUMN item_enrichments.enrichment_type IS 'comments / ecosystem / cross_reference';
COMMENT ON COLUMN item_enrichments.enricher_name IS '产出该条的 enricher 名：hn_comments / github_ecosystem / cross_reference';
COMMENT ON COLUMN item_enrichments.data IS '结构化数据，schema 因 enrichment_type 而异';


-- 2. subjects: 被追踪的事物
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    aliases TEXT[] NOT NULL DEFAULT '{}',
    description TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    first_seen_at DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen_at DATE NOT NULL DEFAULT CURRENT_DATE,
    mention_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subjects_type ON subjects (type);
CREATE INDEX IF NOT EXISTS idx_subjects_last_seen ON subjects (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_subjects_mention_count ON subjects (mention_count DESC);

COMMENT ON TABLE subjects IS '被追踪的事物（project/product/org/person/concept），跨 item 复用';
COMMENT ON COLUMN subjects.slug IS '全局唯一 ID，如 github:owner/repo / product:claude / org:anthropic';
COMMENT ON COLUMN subjects.type IS 'project / product / org / person / concept';
COMMENT ON COLUMN subjects.metadata IS 'type 相关的补充信息：对 project 存 repo 地址/stars/topics 等';


-- 3. subject_mentions: Subject 与 Item 的关联
CREATE TABLE IF NOT EXISTS subject_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    role TEXT NOT NULL DEFAULT 'mentioned',
    source_name TEXT,
    score FLOAT,
    context TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_subject_mentions_key
    ON subject_mentions (subject_id, item_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_subject_mentions_subject ON subject_mentions (subject_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_subject_mentions_item ON subject_mentions (item_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_subject_mentions_date ON subject_mentions (snapshot_date);

COMMENT ON TABLE subject_mentions IS 'Subject 与 Item 的多对多关联，一行 = 某日某条 item 提及了某个 subject';
COMMENT ON COLUMN subject_mentions.role IS 'primary（item 本体就是该 subject） / mentioned（item 顺便提到）';
COMMENT ON COLUMN subject_mentions.score IS '该 item 当时的 aha_index，用于后续画评分趋势';


-- 4. subject_aliases: 人工合并通道
CREATE TABLE IF NOT EXISTS subject_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_slug TEXT UNIQUE NOT NULL,
    to_subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subject_aliases_to ON subject_aliases (to_subject_id);

COMMENT ON TABLE subject_aliases IS '手工合并表：当发现两个 slug 是同一事物时加一行，抽取逻辑自动合并';


-- auto update updated_at trigger（subjects 表）
DO $$
BEGIN
    EXECUTE format(
        'DROP TRIGGER IF EXISTS trigger_update_subjects_updated_at ON subjects; '
        'CREATE TRIGGER trigger_update_subjects_updated_at BEFORE UPDATE ON subjects '
        'FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();'
    );
END;
$$;
