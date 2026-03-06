# scrapers/db.py

import os
import json
from datetime import datetime, timezone, date
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv
from .base import RawItem

load_dotenv()

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

GH_MODELS_TOKEN = os.getenv("GH_MODELS_TOKEN")

# ── AI 关键词过滤 ──────────────────────────────────────────────

AI_KEYWORDS = [
    "LLM", "RAG", "Agent", "Prompt", "Transformer", "Vector Database",
    "Diffusion", "Fine-tuning", "Multi-modal", "Knowledge Graph",
    "Context Window", "Memory module", "Semantic Kernel", "LangChain"
]

def is_ai_related(item: RawItem) -> bool:
    text = f"{item.title} {item.body_text}".lower()
    return any(k.lower() in text for k in AI_KEYWORDS)


# ── AI 加工 ────────────────────────────────────────────────────

def process_with_ai(item: RawItem) -> dict | None:
    if not GH_MODELS_TOKEN:
        return None
    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=GH_MODELS_TOKEN
    )
    prompt = f"""
    作为技术嗅觉敏锐的 AI 专家，分析以下内容并生成中文简报：
    来源: {item.source_name}
    标题: {item.title}
    内容: {item.body_text[:500] if item.body_text else "无"}
    热度指标: {json.dumps(item.raw_metrics, ensure_ascii=False)}

    请输出 JSON（必须包含以下字段）:
    {{
      "processed_title": "吸引人的中文标题",
      "summary": "50字内核心内容总结",
      "category": "tech/finance/entertainment/academic 中选一个最合适的",
      "tags": ["领域标签"],
      "keywords": ["技术关键词，保留英文"],
      "aha_index": 0.0-1.0,
      "expert_insight": "### 🚀 专家点评\\n内容...\\n### 🛠️ 核心干货\\n- 要点..."
    }}
    """
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You only output JSON."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o-mini",
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ AI 处理失败: {item.title} | {e}")
        return None


# ── 写库 ───────────────────────────────────────────────────────

def save_raw_item(item: RawItem):
    """写入 raw_items，已存在则更新 metrics 和 updated_at"""
    supabase.table("raw_items").upsert(
        item.to_db_dict(),
        on_conflict="id"
    ).execute()


def save_processed_item(item: RawItem, ai_data: dict):
    """写入 processed_items，主键 (item_id, snapshot_date)"""
    supabase.table("processed_items").upsert({
        "item_id": item.id,
        "snapshot_date": date.today().isoformat(),
        "raw_title": item.title,
        "original_url": item.original_url,
        "source_name": item.source_name,
        "content_type": item.content_type,
        "author": item.author,
        "raw_metrics": item.raw_metrics,
        "model": "gpt-4o-mini",
        "processed_title": ai_data.get("processed_title"),
        "summary": ai_data.get("summary"),
        "category": ai_data.get("category"),
        "tags": ai_data.get("tags", []),
        "keywords": ai_data.get("keywords", []),
        "aha_index": float(ai_data.get("aha_index", 0.5)),
        "expert_insight": ai_data.get("expert_insight"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="item_id,snapshot_date").execute()


def process_and_save(items: list[RawItem], skip_ai_filter: bool = False):
    """
    统一处理入口，所有抓取脚本调用这一个函数
    skip_ai_filter=True 时跳过关键词过滤（如 AI 公司博客，天然相关）
    """
    filtered = items if skip_ai_filter else [i for i in items if is_ai_related(i)]
    print(f"📊 收到 {len(items)} 条，过滤后 {len(filtered)} 条")

    for item in filtered:
        try:
            save_raw_item(item)
            ai_data = process_with_ai(item)
            if ai_data:
                save_processed_item(item, ai_data)
                print(f"✅ {item.source_name} | {item.title}")
        except Exception as e:
            print(f"❌ 处理失败 ({item.title}): {e}")
