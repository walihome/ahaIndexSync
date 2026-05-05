-- ============================================================
-- Baseline: 线上核心表 DDL 快照（2026-05-05）
-- 本文件仅作文档基线，不在 DB 上执行。
-- 后续 migration 以此为起点。
-- ============================================================

-- ============================================================
-- 1. raw_items: Scraper 输出的不可变元数据快照
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_items (
    id              TEXT PRIMARY KEY,
    -- md5(original_url)

    title           TEXT NOT NULL,
    original_url    TEXT NOT NULL UNIQUE,
    source_name     TEXT DEFAULT 'GitHub',
    source_type     TEXT DEFAULT 'REPO',
    author          TEXT,
    raw_metrics     JSONB,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    content_type    TEXT DEFAULT 'repo',
    body_text       TEXT,
    author_url      TEXT,
    extra           JSONB,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    content_source  TEXT DEFAULT 'scraper',
    content_quality REAL
);

CREATE INDEX IF NOT EXISTS idx_raw_content_type ON raw_items (content_type);
CREATE INDEX IF NOT EXISTS idx_raw_published_at ON raw_items (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_source_name ON raw_items (source_name);

-- 无 trigger（raw_items 的 updated_at 由应用层维护或不维护）

-- ============================================================
-- 2. processed_items: LLM 处理结果
-- ============================================================
CREATE TABLE IF NOT EXISTS processed_items (
    item_id          TEXT NOT NULL REFERENCES raw_items(id),
    processed_title  TEXT,
    raw_title        TEXT,
    summary          TEXT,
    tags             TEXT[],
    keywords         TEXT[],
    aha_index        DOUBLE PRECISION CHECK (aha_index >= 0 AND aha_index <= 1),
    expert_insight   TEXT,
    updated_at       TIMESTAMPTZ DEFAULT now(),
    original_url     TEXT,
    snapshot_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    source_name      TEXT,
    content_type     TEXT DEFAULT 'repo',
    author           TEXT,
    raw_metrics      JSONB,
    model            TEXT DEFAULT 'gpt-4o-mini',
    category         TEXT,
    generated_at     TIMESTAMPTZ DEFAULT now(),
    display_metrics  JSONB,
    rank_group       TEXT,
    rank_action      TEXT,
    rank_score       REAL,
    rank_detail      JSONB,
    extra            JSONB,
    PRIMARY KEY (item_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_processed_aha ON processed_items (snapshot_date, aha_index DESC);
CREATE INDEX IF NOT EXISTS idx_processed_category ON processed_items (snapshot_date, category);
CREATE INDEX IF NOT EXISTS idx_processed_date ON processed_items (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_processed_rank_action ON processed_items (snapshot_date, rank_action);

-- ============================================================
-- 3. display_items: 前端展示内容
-- ============================================================
CREATE TABLE IF NOT EXISTS display_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processed_item_id TEXT NOT NULL,
    snapshot_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    source_name      TEXT NOT NULL,
    content_type     TEXT NOT NULL,
    original_url     TEXT NOT NULL,
    author           TEXT,
    processed_title  TEXT,
    summary          TEXT,
    category         TEXT,
    tags             TEXT[],
    keywords         TEXT[],
    aha_index        DOUBLE PRECISION NOT NULL CHECK (aha_index >= 0 AND aha_index <= 1),
    expert_insight   TEXT,
    display_metrics  JSONB,
    raw_metrics      JSONB,
    rank             INTEGER NOT NULL,
    model            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    rank_group       TEXT,
    extra            JSONB,
    UNIQUE (snapshot_date, rank)
);

CREATE INDEX IF NOT EXISTS idx_display_aha ON display_items (snapshot_date, aha_index DESC);
CREATE INDEX IF NOT EXISTS idx_display_category ON display_items (snapshot_date, category);
CREATE INDEX IF NOT EXISTS idx_display_date ON display_items (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_display_date_rank ON display_items (snapshot_date, rank);

-- ============================================================
-- 4. daily_archives: 每日归档
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_archives (
    snapshot_date       DATE PRIMARY KEY,
    aha_score           NUMERIC,
    aha_delta           NUMERIC,
    item_count          INTEGER,
    top_story_title     TEXT,
    top_story_source    TEXT,
    top_tags            TEXT[],
    rarity_score        INTEGER,
    timeliness_score    INTEGER,
    impact_score        INTEGER,
    created_at          TIMESTAMPTZ DEFAULT now(),
    percentile_90d      DOUBLE PRECISION,
    percentile_tier     TEXT,
    sample_size_90d     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_daily_archives_date ON daily_archives (snapshot_date DESC);

-- ============================================================
-- 5. weekly_archives: 每周归档
-- ============================================================
CREATE TABLE IF NOT EXISTS weekly_archives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    year            INTEGER NOT NULL,
    week_number     INTEGER NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    edition_count   INTEGER,
    item_count      INTEGER,
    avg_aha_score   NUMERIC,
    peak_aha_score  NUMERIC,
    peak_date       DATE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (year, week_number)
);

CREATE INDEX IF NOT EXISTS idx_weekly_archives_date ON weekly_archives (start_date);
CREATE INDEX IF NOT EXISTS idx_weekly_archives_lookup ON weekly_archives (year DESC, week_number DESC);

-- ============================================================
-- 6. monthly_archives: 每月归档
-- ============================================================
CREATE TABLE IF NOT EXISTS monthly_archives (
    month           DATE PRIMARY KEY,
    edition_count   INTEGER,
    item_count      INTEGER,
    avg_aha_score   NUMERIC,
    peak_aha_score  NUMERIC,
    peak_date       DATE,
    summary         TEXT,
    meta_description TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_monthly_archives_month ON monthly_archives (month DESC);

-- ============================================================
-- 7. scraper_configs: 抓取源配置（当前状态快照）
-- ============================================================
-- 已在 001_config_tables.sql 中定义，此处记录终态：
-- id UUID PK, scraper_type TEXT, name TEXT, enabled BOOLEAN,
-- priority INT, config JSONB, created_at, updated_at
-- 无 slug / source_type / content_type 顶层列（阶段 1 新增）
