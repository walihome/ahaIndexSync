import os
import hashlib
import json
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# 加载环境变量
load_dotenv()

# 配置
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GH_MODELS_TOKEN = os.getenv("GH_MODELS_TOKEN") # 既用于 AI，也用于 GitHub API 鉴权

# AI 核心关键词雷达
AI_KEYWORDS = [
    "LLM", "RAG", "Agent", "Prompt", "Transformer", "Vector Database", 
    "Diffusion", "Fine-tuning", "Multi-modal", "Knowledge Graph", 
    "Context Window", "Memory module", "Semantic Kernel", "LangChain"
]

# 初始化 Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def get_trending_repos():
    """抓取 GitHub Trending 数据 (Top 25)"""
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        repos = []
        for article in soup.find_all("article", class_="Box-row"):
            title_tag = article.find("h2", class_="h3")
            full_name = title_tag.text.strip().replace("
", "").replace(" ", "") if title_tag else ""
            repo_url = f"https://github.com{title_tag.find('a')['href']}" if title_tag else ""
            
            desc_tag = article.find("p", class_="col-9")
            description = desc_tag.text.strip() if desc_tag else ""
            
            # 基础指标
            meta = article.find("div", class_="f6 color-fg-muted mt-2")
            stars = 0
            if meta:
                s_link = meta.find("a", href=lambda x: x and x.endswith("/stargazers"))
                if s_link: stars = int(s_link.text.strip().replace(",", ""))

            repos.append({
                "title": full_name,
                "url": repo_url,
                "description": description,
                "author": full_name.split("/")[0] if "/" in full_name else "",
                "metrics": {"stars": stars, "source": "trending"}
            })
        return repos
    except Exception as e:
        print(f"⚠️ Trending 抓取失败: {e}")
        return []

def get_discovery_repos():
    """通过 GitHub API 主动搜索发现黑马项目"""
    if not GH_MODELS_TOKEN: return []
    
    headers = {"Authorization": f"token {GH_MODELS_TOKEN}"}
    base_url = "https://api.github.com/search/repositories"
    
    # 搜索维度：1.一周内星数>100的AI项目 2.一月内星数>1000的项目
    last_week = (datetime.now() - timedelta(days=7)).date()
    last_month = (datetime.now() - timedelta(days=30)).date()
    
    queries = [
        f"topic:ai created:>{last_week} stars:>100",
        f"created:>{last_month} stars:>1000 LLM",
        f"topic:llm pushed:>{last_week} forks:>50"
    ]
    
    discovered = []
    for q in queries:
        try:
            res = requests.get(base_url, headers=headers, params={"q": q, "sort": "stars", "order": "desc"}, timeout=15)
            if res.status_code == 200:
                items = res.json().get("items", [])
                for item in items:
                    discovered.append({
                        "title": item["full_name"],
                        "url": item["html_url"],
                        "description": item["description"] or "",
                        "author": item["owner"]["login"],
                        "metrics": {"stars": item["stargazers_count"], "source": "search_api"}
                    })
        except Exception as e:
            print(f"⚠️ Search API 异常 ({q}): {e}")
    return discovered

def process_with_ai(repo):
    """使用 GPT-4o-mini 进行深度加工"""
    if not GH_MODELS_TOKEN: return None
    client = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=GH_MODELS_TOKEN)

    prompt = f"""
    作为一名技术嗅觉敏锐的 AI 专家，分析以下 GitHub 项目并生成中文简报：
    项目: {repo['title']}
    描述: {repo['description']}
    热度: {repo['metrics']['stars']} stars.

    请输出 JSON 格式（必须包含以下字段）:
    {{
      "processed_title": "惊艳且吸引人的中文标题",
      "summary": "50字内核心功能总结",
      "tags": ["领域标签", "成熟度"],
      "keywords": ["技术关键词(保留英文)"],
      "aha_index": 0.0-1.0评分,
      "expert_insight": "### 🚀 专家点评 
 内容... 
 ### 🛠️ 核心干货 
 - 要点..."
    }}
    """
    try:
        response = client.chat.completions.create(
            messages=[{"role": "system", "content": "You only output JSON."}, {"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ AI 总结失败: {repo['title']} | {e}")
        return None

def save_to_db(repo, ai_data):
    """保存到 Supabase (v2.5 架构：冗余 original_url)"""
    if not supabase: return
    item_id = hashlib.md5(repo["url"].encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    # 1. Raw Layer
    try:
        supabase.table("raw_items").upsert({
            "id": item_id, "title": repo["title"], "original_url": repo["url"],
            "source_name": "GitHub", "source_type": "REPO", "author": repo["author"],
            "raw_metrics": repo["metrics"], "published_at": now
        }).execute()

        # 2. Processed Layer (增加冗余 original_url)
        if ai_data:
            supabase.table("processed_items").upsert({
                "item_id": item_id,
                "raw_title": repo["title"],
                "processed_title": ai_data.get("processed_title"),
                "original_url": repo["url"], # 冗余 URL，方便前端跳转
                "summary": ai_data.get("summary"),
                "tags": ai_data.get("tags", []),
                "keywords": ai_data.get("keywords", []),
                "aha_index": float(ai_data.get("aha_index", 0.5)),
                "expert_insight": ai_data.get("expert_insight"),
                "updated_at": now
            }).execute()
            print(f"✅ 已入库: {repo['title']}")
    except Exception as e:
        print(f"❌ DB 写入失败 ({repo['title']}): {e}")

def main():
    print(f"🚀 Aha Index 侦测启动 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 多源抓取
    trending = get_trending_repos()
    discovery = get_discovery_repos()
    
    # 2. 合并并按 URL 去重
    combined = {repo["url"]: repo for repo in (trending + discovery)}.values()
    
    # 3. 过滤并处理
    ai_repos = [r for r in combined if any(k.lower() in (r["title"] + " " + r["description"]).lower() for k in AI_KEYWORDS)]
    print(f"📊 总抓取: {len(combined)}, 经过 AI 关键词过滤: {len(ai_repos)}")
    
    for repo in ai_repos:
        ai_data = process_with_ai(repo)
        save_to_db(repo, ai_data)
    
    print("✨ 任务完成。")

if __name__ == "__main__":
    main()
