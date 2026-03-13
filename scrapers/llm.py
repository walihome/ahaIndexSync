# infra/llm.py

import os
import json
import time
from pathlib import Path
from openai import OpenAI
from .models import RawItem

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
MODEL = "kimi-k2.5"

REQUEST_INTERVAL = 0.5
MAX_RETRIES = 3

# 模块启动时读一次，不在每次调用时重复 IO
_persona_dir = Path(__file__).parent.parent / "persona"
IDEA_GUIDE    = (_persona_dir / "idea.md").read_text(encoding="utf-8") if (_persona_dir / "idea.md").exists() else ""
SCORING_GUIDE = (_persona_dir / "scoring.md").read_text(encoding="utf-8") if (_persona_dir / "scoring.md").exists() else ""

# 针对不同内容类型的差异化 summary 要求
SUMMARY_GUIDE = {
    "repo": """
summary 必须回答以下三个问题（2-3句话，不超过150字）：
  1. 这个项目解决了什么具体痛点？（不要说"提供了一个框架"这种废话）
  2. 和同类工具（如 LangChain、AutoGen、CrewAI、LlamaIndex 等）的核心差异是什么？
  3. 适合什么场景或什么类型的开发者使用？
""",
    "article": """
summary 必须回答以下两个问题（2句话，不超过100字）：
  1. 核心观点或发现是什么？（具体事实，不要泛泛而谈）
  2. 对读者有什么直接价值或影响？
""",
    "default": """
summary（2句话，不超过100字）：
  第1句：这是什么/做了什么（事实）
  第2句：为什么值得关注/对读者有什么用（价值）
  不要重复标题，不要说废话如"这是一个..."
""",
}


def process_with_ai(item: RawItem) -> dict | None:
    if not KIMI_API_KEY:
        print("⚠️ KIMI_API_KEY 未设置，跳过 AI 处理")
        return None

    client = OpenAI(
        base_url="https://api.moonshot.cn/v1",
        api_key=KIMI_API_KEY,
    )

    summary_guide = SUMMARY_GUIDE.get(item.content_type, SUMMARY_GUIDE["default"])

    prompt = f"""
你是一个 AI 技术日报的资深编辑，风格参考 TLDR Newsletter：信息密度高、直击重点、让读者 5 秒内判断是否值得深读。

读者是 AI 工程师和创业者，他们时间有限，需要你帮他们快速过滤噪音。

待分析内容：
来源: {item.source_name}
来源类型: {item.extra.get('source_tag', '')}
标题: {item.title}
内容: {item.body_text if item.body_text else "无"}
热度指标: {json.dumps(item.raw_metrics, ensure_ascii=False)}
语言/技术栈: {item.extra.get('language', '') or ', '.join(item.extra.get('topics', []))}

请输出 JSON，字段要求如下：

processed_title:
  - 15字以内中文标题
  - 突出"解决了什么问题"或"做了什么"，而不是复述原标题
  - 好的例子："无需 LangChain 的轻量 AI Agent 框架"、"用 RAG 把幻觉率降低 60%"
  - 坏的例子："关于大型语言模型的工具"、"AI 代理新框架介绍"

{summary_guide}

tags:
  - 最多3个
  - 优先写具体名称：产品名、技术名、框架名（如 LangChain、RAG、Llama）
  - 禁止写泛泛标签：AI、机器学习、人工智能、开源（除非是核心卖点）

keywords: 英文技术关键词，2-5个

category: 从以下选一个: tech / finance / entertainment / academic

aha_index:
  - 0.0-1.0 浮点数
  - 严格按照以下打分标准逐步计算，不要凭感觉估分：
{SCORING_GUIDE}
  - 打分时优先关注以下类型内容（编辑价值判断）：
{IDEA_GUIDE}
  - 同时输出打分过程：
    "aha_score_detail": {{
      "base": 2,
      "bonus": ["时效性", "实用性"],
      "penalty": [],
      "raw_score": 4,
      "aha_index": 0.50
    }}

expert_insight:
  - 格式固定，总字数不超过200字
  - ### 🎯 核心价值
  - （对读者最直接的价值，一句话）
  - ### 🛠️ 关键亮点
  - 亮点1（具体，不要泛泛）
  - 亮点2
  - ### ⚔️ 与同类对比
  - （工具/框架类内容说清楚差异点；非工具类填"N/A"）
  - ### ⚡ 为什么现在值得关注
  - （时效性或行业背景）
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You only output JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=MODEL,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            result["model"] = MODEL

            # 从 aha_score_detail 提取最终分，保证一致性
            detail = result.get("aha_score_detail", {})
            if detail.get("aha_index") is not None:
                result["aha_index"] = detail["aha_index"]

            time.sleep(REQUEST_INTERVAL)
            return result

        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "overloaded" in err_str

            if is_rate_limit and attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 2)  # 4s → 8s → 16s
                print(f"  ⏳ 限流，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES}): {item.title[:40]}")
                time.sleep(wait)
                continue

            print(f"⚠️ AI 处理失败: {item.title} | {e}")
            return None

    return None
