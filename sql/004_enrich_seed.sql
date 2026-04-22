-- ============================================================
-- AhaIndexSync - Enrich 阶段配套 seed：params + prompts
-- 依赖 003_enrich_and_subject_tables.sql
-- ============================================================

-- ── 1. pipeline_params ──────────────────────────────────────

INSERT INTO pipeline_params (key, value, description) VALUES
('enrich_enabled', 'true', 'Enrich 阶段总开关，关闭后等同于旧管道'),
('enrich_timeout', '3600', 'Enrich 阶段整体超时秒数，超时后已写入数据保留、后续跳过'),
('enrich_max_workers', '5', 'Enrich 阶段 item 级并发线程数'),
('coarse_filter_min_aha', '0.25', '粗排阶段 aha_index 下限，低于此值直接排除')
ON CONFLICT (key) DO NOTHING;


-- ── 2. enrich 阶段 prompt 模板 ─────────────────────────────

-- HN Comments 分析
INSERT INTO prompt_templates (name, stage, template, model, temperature, max_retries, request_interval) VALUES
('enrich_hn_comments', 'enrich', E'你是 AI 日报的社区情报分析师。以下是 HackerNews 某篇文章按点赞排序的 Top 评论，请从中提炼出对 AI 从业者有价值的社区视角。\n\n文章标题：{title}\n文章摘要：{summary}\n\n评论列表（按 points 降序，格式：[points] 作者: 内容）：\n{comments_text}\n\n请输出 JSON，字段如下：\n\nsentiment:\n  - positive / mixed / negative\n  - 判断依据：评论整体是支持还是质疑、吐槽多还是赞赏多\n\ncore_debate:\n  - 一句话（40 字以内）概括评论区最核心的争论点或共识\n  - 例："评论认为相比 ComfyUI-MCP 更轻量但功能不完整"\n\ntop_insights:\n  - 长度 2-3\n  - 每条包含 point（观点，30 字以内）和 author（作者名）\n  - 挑选最有信息量、最有个人经验/数据支撑的评论\n\nalternatives:\n  - 评论中被拿来对比的替代方案名称，字符串数组\n  - 如果评论里有 GitHub 链接，额外放进 alternative_repos（格式 owner/repo）\n  - 没有则留空数组\n\nalternative_repos:\n  - GitHub repo 形式（owner/repo）的数组，仅当评论中出现 github.com/xxx/yyy 链接时填充\n\nvaluable_links:\n  - 评论中引用的外部高价值链接，字符串数组\n  - 不包含原文链接、不包含 HN 自引用\n\n只输出 JSON，不要任何额外解释。', 'kimi-k2.5', 0.2, 2, 0.3)
ON CONFLICT (name) DO NOTHING;

-- GitHub Ecosystem 分析
INSERT INTO prompt_templates (name, stage, template, model, temperature, max_retries, request_interval) VALUES
('enrich_github_ecosystem', 'enrich', E'你是 AI 领域的开源生态观察员。给定目标 repo 及通过 topics 搜索到的同赛道 repo 列表，请判断其生态位置。\n\n目标 repo：\n名称：{repo_full_name}\nstars：{stars}\ntopics：{topics}\n描述：{description}\nREADME 片段：{readme_excerpt}\n\n同赛道搜索结果（最多 10 条）：\n{candidates_text}\n\n请输出 JSON：\n\ncompetitors:\n  - 长度 0-5，每项含 name（owner/repo）、stars（int）、comparison（30 字内与目标的差异）\n  - 只列真正同赛道的竞品，搜索结果中不相关的剔除\n\necosystem_position:\n  - 一句话（40 字内）定位该项目在生态中的角色\n\nmaturity:\n  - experimental / beta / production，三选一\n\nunique_value:\n  - 一句话（40 字内）说明相比竞品的独特价值\n\n只输出 JSON。', 'kimi-k2.5', 0.2, 2, 0.3)
ON CONFLICT (name) DO NOTHING;
