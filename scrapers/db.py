# scrapers/db.py

import os
import json
from datetime import datetime, timezone, date
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv
from .base import RawItem
from .displayMetrics import DISPLAY_METRICS_CONFIG

load_dotenv()

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
    if not GEMINI_API_KEY:
        return None
    client = OpenAI(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=GEMINI_API_KEY
    )
    prompt = f"""
    作为技术嗅觉敏锐的 AI 专家，分析以下内容并生成中文简报：
    来源: {item.source_name}
    来源类型: {item.extra.get('source_tag', '')}
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
            model="gemini-2.0-flash",
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ AI 处理失败: {item.title} | {e}")
        return None


# ── build_display_metrics ──────────────────────────────────────

def build_display_metrics(item: RawItem) -> dict:
    """根据 content_type 配置，从 raw_metrics / extra 组装前端展示字段"""
    config = DISPLAY_METRICS_CONFIG.get(item.content_type, [])
    data = {
        **item.extra,
        **item.raw_metrics,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "source_name":  item.source_name,
    }
    result = []
    for field in config:
        key = field["key"]
        fmt = field["format"]
        val = data.get(key)
        if val is None:
            continue
        if fmt == "number":
            display = f"{int(val):,}"
        elif fmt == "days_ago":
            created = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - created).days
            display = "今天" if days == 0 else f"{days} 天前"
        elif fmt == "date":
            display = str(val)[:10].replace("-", "/")
        else:
            display = str(val)
        result.append({"label": field["label"], "value": display})
    return {"items": result}


# ── 写库 ───────────────────────────────────────────────────────

def save_raw_item(item: RawItem):
    result = supabase.table("raw_items").upsert(
        item.to_db_dict()
    ).execute()
    if not result.data:
        raise Exception(f"save_raw_item 写入失败: {item.title}")


def save_processed_item(item: RawItem, ai_data: dict):
    result = supabase.table("processed_items").upsert({
        "item_id": item.id,
        "snapshot_date": date.today().isoformat(),
        "raw_title": item.title,
        "original_url": item.original_url,
        "source_name": item.source_name,
        "content_type": item.content_type,
        "author": item.author,
        "raw_metrics": item.raw_metrics,
        "model": "gemini-2.0-flash",
        "processed_title": ai_data.get("processed_title"),
        "summary": ai_data.get("summary"),
        "category": ai_data.get("category"),
        "tags": ai_data.get("tags", []),
        "keywords": ai_data.get("keywords", []),
        "aha_index": float(ai_data.get("aha_index", 0.5)),
        "expert_insight": ai_data.get("expert_insight"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "display_metrics": build_display_metrics(item),
    }).execute()
    if not result.data:
        raise Exception(f"save_processed_item 写入失败: {item.title}")


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
