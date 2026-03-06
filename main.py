 import os
 import hashlib
 import json
 import requests
 from bs4 import BeautifulSoup
 from openai import OpenAI
 from supabase import create_client, Client
 from dotenv import load_dotenv
 from datetime import datetime, timezone

 # 加载环境变量
 load_dotenv()

 # 配置
 SUPABASE_URL = os.getenv("SUPABASE_URL")
 SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
 GH_MODELS_TOKEN = os.getenv("GH_MODELS_TOKEN")

 # 增强版 AI 关键词雷达
 AI_KEYWORDS = [
     "LLM", "RAG", "Agent", "Prompt", "Transformer", "Vector Database",
     "Diffusion", "Fine-tuning", "Multi-modal", "Knowledge Graph",
     "Context Window", "Memory module", "Semantic Kernel", "LangChain"
 ]

 # 初始化 Supabase
 supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

 def get_trending_repos():
     """抓取 GitHub Trending 并提取深度指标 (Stars/Forks)"""
     url = "https://github.com/trending"
     headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

     try:
         response = requests.get(url, headers=headers, timeout=15)
         response.raise_for_status()
     except Exception as e:
         print(f"❌ 抓取失败: {e}")
         return []

     soup = BeautifulSoup(response.text, "html.parser")
     repos = []

     for article in soup.find_all("article", class_="Box-row"):
         # 1. 基础信息
         title_tag = article.find("h2", class_="h3")
         full_name = title_tag.text.strip().replace("\n", "").replace(" ", "") if title_tag else ""
         repo_url = f"https://github.com{title_tag.find('a')['href']}" if title_tag and title_tag.find('a') else ""

         # 2. 描述
         desc_tag = article.find("p", class_="col-9")
         description = desc_tag.text.strip() if desc_tag else ""

         # 3. 抓取指标 (Metrics)
         meta_data = article.find("div", class_="f6 color-fg-muted mt-2")
         stars = 0
         forks = 0
         stars_today = 0

         if meta_data:
             # 查找 Stars
             star_link = meta_data.find("a", href=lambda x: x and x.endswith("/stargazers"))
             if star_link:
                 stars = int(star_link.text.strip().replace(",", ""))

             # 查找 Forks
             fork_link = meta_data.find("a", href=lambda x: x and x.endswith("/forks"))
             if fork_link:
                 forks = int(fork_link.text.strip().replace(",", ""))

             # 查找今日增长
             today_span = meta_data.find("span", class_="d-inline-block float-sm-right")
             if today_span:
                 stars_today = int(today_span.text.strip().split()[0].replace(",", ""))

         repos.append({
             "title": full_name,
             "description": description,
             "url": repo_url,
             "author": full_name.split("/")[0] if "/" in full_name else "",
             "metrics": {
                 "stars": stars,
                 "forks": forks,
                 "stars_today": stars_today
             }
         })
     return repos

 def filter_ai_repos(repos):
     """基于关键词过滤 AI 相关项目"""
     return [
         r for r in repos
         if any(k.lower() in (r["title"] + " " + r["description"]).lower() for k in AI_KEYWORDS)
     ]

 def process_with_ai(repo):
     """使用 GitHub Models (GPT-4o-mini) 进行深度加工"""
     if not GH_MODELS_TOKEN:
         return None

     client = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=GH_MODELS_TOKEN)

     # 完善 Prompt，要求生成双标题和高含金量洞察
     prompt = f"""
     作为一名顶尖 AI 架构师，分析以下 GitHub 项目并生成中文简报：
     项目名称: {repo['title']}
     项目描述: {repo['description']}
     热度数据: {repo['metrics']['stars_today']} stars added today, total {repo['metrics']['stars']} stars.

     请输出结构化 JSON (严格遵守以下字段):
     {{
       "processed_title": "一个极其抓人眼球、体现技术突破的中文短标题",
       "summary": "一句话核心功能摘要 (中肯、专业、50字内)",
       "tags": ["领域标签(如: RAG, 自动化)", "成熟度(如: SOTA, 实验性)"],
       "keywords": ["英文技术关键词1", "关键词2"],
       "aha_index": 0.0到1.0的评分 (0.9以上代表突破性发现),
       "expert_insight": "### 🚀 专家点评 \\n 从技术底层分析其价值... \\n ### 🛠️ 核心干货 \\n - 关键点1 \\n - 关键点2"
     }}
     """

     try:
         response = client.chat.completions.create(
             messages=[
                 {"role": "system", "content": "你只输出 JSON。你是技术嗅觉极其敏锐的 AI 专家。"},
                 {"role": "user", "content": prompt}
             ],
             model="gpt-4o-mini",
             response_format={"type": "json_object"}
         )
         return json.loads(response.choices[0].message.content)
     except Exception as e:
         print(f"⚠️ AI 总结失败 ({repo['title']}): {e}")
         return None

 def save_to_db(repo, ai_data):
     """根据 v2.4 架构保存数据 (支持 raw_metrics 和 冗余 raw_title)"""
     if not supabase: return

     # 使用 URL MD5 作为唯一 ID
     item_id = hashlib.md5(repo["url"].encode()).hexdigest()
     now = datetime.now(timezone.utc).isoformat()

     # 1. 写入 raw_items (原材料层)
     raw_item = {
         "id": item_id,
         "title": repo["title"], # 客观标题
         "original_url": repo["url"],
         "source_name": "GitHub",
         "source_type": "REPO",
         "author": repo["author"],
         "raw_metrics": repo["metrics"], # 存储 Stars/Forks JSON
         "published_at": now
     }

     try:
         supabase.table("raw_items").upsert(raw_item).execute()
     except Exception as e:
         print(f"❌ raw_items 写入错误: {e}")
         return

     # 2. 写入 processed_items (加工层)
     if ai_data:
         processed_item = {
             "item_id": item_id,
             "raw_title": repo["title"],       # 冗余存储，方便单表查询
             "processed_title": ai_data.get("processed_title"), # AI 生成的惊艳标题
             "summary": ai_data.get("summary"),
             "tags": ai_data.get("tags", []),
             "keywords": ai_data.get("keywords", []),
             "aha_index": float(ai_data.get("aha_index", 0.5)),
             "expert_insight": ai_data.get("expert_insight"),
             "updated_at": now
         }
         try:
             supabase.table("processed_items").upsert(processed_item).execute()
             print(f"✅ 已成功加工并入库: {repo['title']} (Aha: {processed_item['aha_index']})")
         except Exception as e:
             print(f"❌ processed_items 写入错误: {e}")

 def main():
     print(f"🚀 Aha Index 侦测启动 | 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

     all_repos = get_trending_repos()
     ai_repos = filter_ai_repos(all_repos)
     print(f"📊 发现 {len(all_repos)} 个趋势项目，其中 {len(ai_repos)} 个符合 AI 过滤标准。")

     for repo in ai_repos:
         ai_data = process_with_ai(repo)
         save_to_db(repo, ai_data)

     print("✨ 任务完成。")

 if __name__ == "__main__":
     main()
