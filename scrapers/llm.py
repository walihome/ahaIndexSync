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
你是一个 AI 技术日报的资深编辑，风格参考 TLDR Newsletter：信息密度高、直击重点、让读者 5 秒内判断是否值得深读。

读者是 AI 工程师和创业者，他们时间有限，需要你帮他们快速过滤噪音。

待分析内容：
来源: {item.source_name}
来源类型: {item.extra.get('source_tag', '')}
标题: {item.title}
内容: {item.body_text[:800] if item.body_text else "无"}
热度指标: {json.dumps(item.raw_metrics, ensure_ascii=False)}

请输出 JSON，字段要求如下：

processed_title:
  - 15字以内中文标题
  - 突出"做了什么"或"解决了什么问题"，而不是复述原标题
  - 好的例子："Meta 开源最强多模态模型 Llama 4"、"用 RAG 把幻觉率降低 60%"
  - 坏的例子："关于大型语言模型的工具"、"AI 代理新框架介绍"

summary:
  - 2句话，不超过60字
  - 第1句：这是什么/做了什么（事实）
  - 第2句：为什么值得关注/对读者有什么用（价值）
  - 不要重复标题，不要说废话如"这是一个..."

tags:
  - 最多3个
  - 优先写具体名称：产品名、技术名、框架名（如 LangChain、RAG、Llama）
  - 禁止写泛泛标签：AI、机器学习、人工智能、开源（除非是核心卖点）

keywords: 英文技术关键词，2-5个

category: 从以下选一个: tech / finance / entertainment / academic

aha_index:
  - 0.0-1.0 浮点数
  - 参考：大厂官方重大发布=0.85-0.95，热门开源新工具=0.65-0.80，普通资讯=0.40-0.60
  - 热度指标（stars/score）高的可以适当加分

expert_insight:
  - 格式固定，总字数不超过150字
  - ### 🎯 一句话价值
  - （对读者最直接的价值）
  - ### 🛠️ 核心亮点
  - 亮点1
  - 亮点2
  - ### ⚡ 为什么现在值得关注
  - （时效性或行业背景）
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
