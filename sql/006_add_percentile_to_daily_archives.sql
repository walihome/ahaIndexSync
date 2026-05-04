-- ============================================================
-- 给 daily_archives 表新增分位数字段
-- 用于前端"值得看指数"的稀缺信号展示
-- ============================================================

ALTER TABLE daily_archives ADD COLUMN IF NOT EXISTS percentile_90d FLOAT;
ALTER TABLE daily_archives ADD COLUMN IF NOT EXISTS percentile_tier TEXT;
ALTER TABLE daily_archives ADD COLUMN IF NOT EXISTS sample_size_90d INT;

COMMENT ON COLUMN daily_archives.percentile_90d IS '今日分数在近 90 天窗口内的百分位（0-1）';
COMMENT ON COLUMN daily_archives.percentile_tier IS '分位档：p90_plus / p70_p90 / below_p70 / insufficient_data';
COMMENT ON COLUMN daily_archives.sample_size_90d IS '近 90 天可用样本天数';
