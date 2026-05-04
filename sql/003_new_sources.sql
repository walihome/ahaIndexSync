-- 新增 3 个数据源：Reddit / HuggingFace / Product Hunt

-- 1. scraper_configs
INSERT INTO scraper_configs (scraper_type, name, priority, config) VALUES ('reddit', 'Reddit r/LocalLLaMA', 35, '{"source_type":"NEWS","content_type":"reddit","subreddit":"LocalLLaMA","min_score":50,"skip_nsfw":true,"skip_stickied":true,"skip_discussion_below":100,"skip_self_text_below":200,"max_retries":3,"source_tag":"ai_community"}');
INSERT INTO scraper_configs (scraper_type, name, priority, config) VALUES ('reddit', 'Reddit r/MachineLearning', 35, '{"source_type":"NEWS","content_type":"reddit","subreddit":"MachineLearning","min_score":50,"skip_nsfw":true,"skip_stickied":true,"skip_discussion_below":100,"skip_self_text_below":200,"max_retries":3,"source_tag":"ai_community"}');
INSERT INTO scraper_configs (scraper_type, name, priority, config) VALUES ('hf_papers', 'HuggingFace Papers', 55, '{"source_type":"ARTICLE","content_type":"hf_papers","top_n":3,"max_retries":3,"source_tag":"ai_research"}');
INSERT INTO scraper_configs (scraper_type, name, priority, config) VALUES ('hf_model', 'HuggingFace Models', 56, '{"source_type":"REPO","content_type":"hf_model","min_likes":50,"min_downloads":1000,"limit":3,"max_retries":3,"source_tag":"ai_model"}');
INSERT INTO scraper_configs (scraper_type, name, priority, config) VALUES ('product_hunt', 'Product Hunt', 65, '{"source_type":"PRODUCT","content_type":"product_hunt","min_votes":200,"max_retries":3,"topic_whitelist":["artificial-intelligence","developer-tools","productivity","chatbots","no-code","open-source","machine-learning"],"topic_blacklist":["crypto","web3","nft","blockchain","defi","dao","token"],"source_tag":"product_hunt"}');

-- 2. rank_group_configs
UPDATE rank_group_configs SET source_names = ARRAY['GitHub Trending','GitHub Search','HuggingFace Models'] WHERE group_name = '开源项目';
UPDATE rank_group_configs SET source_names = ARRAY['HackerNews','Reddit r/LocalLLaMA','Reddit r/MachineLearning'], "limit" = 10 WHERE group_name = '技术社区';
UPDATE rank_group_configs SET source_names = ARRAY['Huggingface Daily Papers','HuggingFace Papers'] WHERE group_name = '学术论文';
INSERT INTO rank_group_configs (group_name, source_names, "limit", must_include, sort_order) VALUES ('AI 产品', ARRAY['Product Hunt'], 3, false, 25);

-- 3. display_metrics_configs
INSERT INTO display_metrics_configs (content_type, metrics) VALUES ('reddit', '[{"label":"score","key":"score","format":"number"},{"label":"comments","key":"comments","format":"number"}]');
INSERT INTO display_metrics_configs (content_type, metrics) VALUES ('hf_papers', '[{"label":"upvotes","key":"upvotes","format":"number"},{"label":"comments","key":"num_comments","format":"number"}]');
INSERT INTO display_metrics_configs (content_type, metrics) VALUES ('hf_model', '[{"label":"likes","key":"likes","format":"number"},{"label":"downloads","key":"downloads","format":"number"}]');
INSERT INTO display_metrics_configs (content_type, metrics) VALUES ('product_hunt', '[{"label":"votes","key":"votes","format":"number"},{"label":"comments","key":"comments","format":"number"}]');
