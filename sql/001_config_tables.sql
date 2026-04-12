-- ============================================================
-- AhaIndexSync 配置化重构 - 建表 SQL
-- 执行顺序：先建表，再插入 seed 数据
-- ============================================================

-- 1. scraper_configs: 抓取源配置
CREATE TABLE IF NOT EXISTS scraper_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scraper_type TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    priority INT NOT NULL DEFAULT 100,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scraper_configs_type ON scraper_configs (scraper_type);
CREATE INDEX IF NOT EXISTS idx_scraper_configs_enabled ON scraper_configs (enabled) WHERE enabled = true;

COMMENT ON TABLE scraper_configs IS '抓取源配置，每行 = 一个引擎 + 一套参数';
COMMENT ON COLUMN scraper_configs.scraper_type IS '引擎类型：github_trending, github_search, hackernews, rss, twitter_twscrape, twitter_nitter, ai_blog, community_v2ex, community_linuxdo';
COMMENT ON COLUMN scraper_configs.name IS '显示名，写入 raw_items.source_name';
COMMENT ON COLUMN scraper_configs.config IS '引擎专属参数 JSON，schema 因 scraper_type 而异';

-- 2. prompt_templates: Prompt 模板
CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    stage TEXT NOT NULL,
    template TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'kimi-k2.5',
    model_base_url TEXT NOT NULL DEFAULT 'https://api.moonshot.cn/v1',
    temperature FLOAT NOT NULL DEFAULT 0.3,
    max_retries INT NOT NULL DEFAULT 3,
    request_interval FLOAT NOT NULL DEFAULT 0.5,
    enabled BOOLEAN NOT NULL DEFAULT true,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE prompt_templates IS 'Pipeline 各阶段使用的 Prompt 模板';
COMMENT ON COLUMN prompt_templates.stage IS '所属阶段：process / rank / archive';
COMMENT ON COLUMN prompt_templates.template IS 'Prompt 文本，支持 {variable} 占位符';

-- 3. rank_group_configs: 精排分组
CREATE TABLE IF NOT EXISTS rank_group_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name TEXT NOT NULL,
    source_names TEXT[] NOT NULL DEFAULT '{}',
    "limit" INT NOT NULL DEFAULT 5,
    must_include BOOLEAN NOT NULL DEFAULT false,
    sort_order INT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rank_group_configs_enabled ON rank_group_configs (enabled, sort_order);

COMMENT ON TABLE rank_group_configs IS '精排分组配置，决定每日内容的来源分组和数量';

-- 4. tag_slot_configs: 特殊标签每日名额
CREATE TABLE IF NOT EXISTS tag_slot_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tag_name TEXT UNIQUE NOT NULL,
    max_slots INT NOT NULL DEFAULT 1,
    min_score FLOAT NOT NULL DEFAULT 45,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE tag_slot_configs IS '特殊标签每日名额（gossip/deal/macro 等保底机制）';

-- 5. pipeline_params: 全局参数 KV
CREATE TABLE IF NOT EXISTS pipeline_params (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE pipeline_params IS 'Pipeline 全局参数键值对';

-- 6. display_metrics_configs: 前端展示指标配置
CREATE TABLE IF NOT EXISTS display_metrics_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type TEXT UNIQUE NOT NULL,
    metrics JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE display_metrics_configs IS '按 content_type 配置前端展示哪些指标';

-- 7. content_fetch_rules: 正文补全规则
CREATE TABLE IF NOT EXISTS content_fetch_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type TEXT NOT NULL,
    value TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_fetch_rules_type ON content_fetch_rules (rule_type) WHERE enabled = true;

COMMENT ON TABLE content_fetch_rules IS '正文补全规则：skip_domain / fetch_fulltext_tag';

-- 8. pipeline_runs: Pipeline 执行记录
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type TEXT NOT NULL DEFAULT 'daily',
    status TEXT NOT NULL DEFAULT 'running',
    table_suffix TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    config_snapshot JSONB,
    stats JSONB DEFAULT '{}',
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs (status, started_at DESC);

COMMENT ON TABLE pipeline_runs IS 'Pipeline 每次执行的记录，含配置快照和统计';

-- 9. scraper_runs: 单个 Scraper 执行记录
CREATE TABLE IF NOT EXISTS scraper_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    scraper_config_id UUID REFERENCES scraper_configs(id) ON DELETE SET NULL,
    scraper_type TEXT NOT NULL,
    scraper_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    items_fetched INT DEFAULT 0,
    items_saved INT DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_pipeline ON scraper_runs (pipeline_run_id);

COMMENT ON TABLE scraper_runs IS '单个 Scraper 的执行记录';

-- auto update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'scraper_configs', 'prompt_templates', 'rank_group_configs',
            'tag_slot_configs', 'pipeline_params', 'display_metrics_configs'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trigger_update_%s_updated_at ON %I; '
            'CREATE TRIGGER trigger_update_%s_updated_at BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END;
$$;
