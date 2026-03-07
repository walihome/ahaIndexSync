# scrapers/llm.py

import os
import json
from openai import OpenAI
from .base import RawItem

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"

def process_with_ai(item: RawItem) -> dict | None:
    if not GROQ_API_KEY:
        return None
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
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
            model=MODEL,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ AI 处理失败: {item.title} | {e}")
        return None
