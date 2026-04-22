-- ============================================================
-- AhaIndexSync - 将所有 prompt_templates 从 kimi-k2.5 升级到 kimi-k2.6
--
-- 关键前提：kimi-k2.6 默认开启 thinking，会污染 response_format=json_object 的
-- 解析。代码层（infra/llm.py）在调用时已自动注入 "thinking": {"type":"disabled"}，
-- 所以这里只需改 model 名即可。
--
-- 可重复执行：相同 model 再 UPDATE 一次无副作用。
-- ============================================================

UPDATE prompt_templates
SET model = 'kimi-k2.6',
    updated_at = now()
WHERE model = 'kimi-k2.5';

-- 修改默认值（新插入的 prompt 会以 k2.6 为默认）
ALTER TABLE prompt_templates
    ALTER COLUMN model SET DEFAULT 'kimi-k2.6';

-- 同步 base_url 默认值到国际域名（.ai 而非 .cn，kimi-k2.6 官方文档主推）
-- 已有行不变更；如需改动用单独 UPDATE。
ALTER TABLE prompt_templates
    ALTER COLUMN model_base_url SET DEFAULT 'https://api.moonshot.cn/v1';

-- 验证
SELECT model, COUNT(*) AS n
FROM prompt_templates
GROUP BY model
ORDER BY model;
