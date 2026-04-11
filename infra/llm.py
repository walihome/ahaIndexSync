# infra/llm.py

import os
import json
import time
from openai import OpenAI
from .models import RawItem

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
MODEL = "kimi-k2.5"

REQUEST_INTERVAL = 0.5  # 付费版限速宽松，0.5s 足够
MAX_RETRIES = 3


def process_with_ai(item: RawItem) -> dict | None:
    if not KIMI_API_KEY:
        print("⚠️ KIMI_API_KEY 未设置，跳过 AI 处理")
        return None

    client = OpenAI(
        base_url="https://api.moonshot.cn/v1",
        api_key=KIMI_API_KEY,
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
  - 2句话，不超过100字
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
  - 这是编辑点评，是整条内容中最有价值的部分
  - 严格要求：必须写出标题和摘要里没有的信息，禁止复述已有内容
  - 纯文本，不使用 Markdown 格式（不要 ###、不要 **、不要列表符号 -）
  - 总字数 80-150 字，2-3 个自然段落，段落之间用换行分隔

  根据内容类型，侧重点不同：

  如果是开源项目/工具：
    写清楚三件事：这个工具解决的痛点之前大家怎么解决的、跟同类工具（指名道姓）比优势在哪、什么人/场景最该试试。
    好的示例："做 RAG 的团队之前大多用 LangChain + Chroma 的组合，但检索精度一直是痛点。这个框架用混合检索（BM25 + 向量）把准确率拉到了 94%，而且不需要 GPU。\n如果你的 RAG 管线还在用纯向量检索，值得花半小时跑一下它的 benchmark。"

  如果是行业新闻/收购/融资：
    写清楚三件事：背后的战略逻辑、对哪些公司/赛道构成直接威胁或利好、读者需要做什么（调整技术选型、关注新机会、规避风险）。
    好的示例："OpenAI 收 Windsurf 不是为了编辑器本身，而是在补 AI 原生开发工具链这块短板。这意味着 Cursor、Bolt 这些独立 AI IDE 的窗口期在缩短。\n如果你在做 AI 编程工具方向的创业，需要重新评估和 OpenAI 正面竞争的可能性。"

  如果是论文/研究：
    写清楚三件事：核心方法用一句大白话讲清楚（不要学术黑话）、比之前的 SOTA 好在哪好多少、工程落地的可能性（算力需求、有没有开源代码）。
    好的示例："这篇论文的核心思路是让小模型在推理时自我纠错，不需要外部反馈。在 GSM8K 上把 7B 模型的推理准确率从 58% 拉到了 72%，逼近 GPT-4 早期水平。\n代码已开源，如果你在做端侧推理，这个方法的性价比很高。"

  如果是社交媒体/大佬观点：
    写清楚三件事：这个人为什么在这个时间点说这句话、背后可能暗示什么行业信号、哪些人该特别关注。
    好的示例："Karpathy 公开说 LLM 的下一个突破不在模型架构而在数据，这个时间点很微妙——正好是 Llama 4 因为训练数据问题被质疑之后。\n做数据标注、数据清洗、合成数据赛道的团队可以重点关注，行业风向可能在转。"

  如果是其他类型：
    对 AI 从业者意味着什么？有什么可以立刻行动的建议？

  坏的示例（禁止出现类似内容）：
    "掌握CPU分支预测技术，提升算法效率。" → 这是废话，标题已经说了
    "框架持续更新，新增模型支持，对金融交易领域AI应用有重要意义。" → 这是摘要的复述
    "OpenAI 的此次收购可能带来 AI 技术的新突破。" → 这是任何人都能说的空话，没有具体判断
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