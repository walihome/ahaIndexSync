# rank.py
# 精排入口：读 processed_items → 按 rank_config 分组筛选 → 写 display_items
# 每次运行前先清除当天旧数据，保证幂等可重跑

import os
import json
import time
from datetime import date, datetime
from openai import OpenAI
from infra.db import supabase, PROCESSED_TABLE, DISPLAY_TABLE
from config.rank_config import RANK_GROUPS

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
MODEL = "moonshot-v1-8k"


# ── 工具函数 ───────────────────────────────────────────────────

def get_metrics(item: dict) -> dict:
    """把 aha_index 和 raw_metrics 打平，统一取值"""
    return {
        "aha_index": item.get("aha_index", 0),
        **(item.get("raw_metrics") or {}),
    }


def get_sort_value(item: dict, sort_by: str) -> float:
    return get_metrics(item).get(sort_by, 0) or 0


def build_display_row(item: dict, rank: int, today: str) -> dict:
    return {
        "processed_item_id": item["item_id"],
        "snapshot_date": today,
        "source_name": item["source_name"],
        "content_type": item["content_type"],
        "original_url": item["original_url"],
        "author": item.get("author"),
        "processed_title": item.get("processed_title"),
        "summary": item.get("summary"),
        "category": item.get("category"),
        "tags": item.get("tags", []),
        "keywords": item.get("keywords", []),
        "aha_index": item.get("aha_index", 0),
        "expert_insight": item.get("expert_insight"),
        "display_metrics": item.get("display_metrics"),
        "raw_metrics": item.get("raw_metrics"),
        "rank": rank,
        "model": item.get("model"),
    }


# ── AI 二次精排 ────────────────────────────────────────────────

def ai_rerank(candidates: list[dict], group: str, limit: int) -> list[dict]:
    """把候选内容喂给大模型，让它选出最值得推的 limit 条并重新生成摘要"""
    if not KIMI_API_KEY or not candidates:
        # 无 API key 时降级为按 aha_index 排序
        return sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)[:limit]

    client = OpenAI(base_url="https://api.moonshot.cn/v1", api_key=KIMI_API_KEY)

    candidate_text = "\n\n".join([
        f"[{i+1}] 来源:{c['source_name']}\n标题:{c.get('processed_title') or c.get('raw_title')}\n摘要:{c.get('summary', '')}"
        for i, c in enumerate(candidates)
    ])
    # 读取 persona
    with open("persona/idea.md", "r") as f:
        persona = f.read()

    prompt = f"""
你是 AI 日报编辑，负责从以下「{group}」候选内容中，选出最值得读者关注的 {limit} 条。

候选内容：
{candidate_text}

选择标准：
1. 信息增量高，读者看完有收获
2. 避免重复或同质化内容
3. 优先选择有实际影响的新闻或工具

以下类型内容应优先给高分（参考编辑标准）：
{persona}

请输出 JSON，格式如下：
{{
  "selected": [1, 3],  // 选中的编号列表，从1开始
}}
"""

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
        selected_indices = [i - 1 for i in result.get("selected", []) if 1 <= i <= len(candidates)]
        time.sleep(0.5)
        return [candidates[i] for i in selected_indices[:limit]]
    except Exception as e:
        print(f"  ⚠️ AI 精排失败 ({group}): {e}，降级为 aha_index 排序")
        return sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)[:limit]


# ── 主流程 ─────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    today = date.today().isoformat()
    print(f"\n🏆 精排启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 读取今日所有 processed_items
    data = (
        supabase.table(PROCESSED_TABLE)
        .select("*")
        .eq("snapshot_date", today)
        .execute()
        .data
    )
    print(f"📋 今日 processed_items 共 {len(data)} 条\n")

    if not data:
        print("✅ 无数据，退出")
        return

    # 按 source_name 建索引，方便分组查找
    source_map: dict[str, list[dict]] = {}
    for item in data:
        source_map.setdefault(item["source_name"], []).append(item)

    # 清除今天旧的 display_items，保证幂等
    supabase.table(DISPLAY_TABLE).delete().eq("snapshot_date", today).execute()
    print(f"🗑️  已清除今日旧数据\n")

    rank = 1
    rows_to_insert = []

    for group_cfg in RANK_GROUPS:
        group = group_cfg["group"]
        sources = group_cfg["sources"]
        limit = group_cfg["limit"]
        sort_by = group_cfg["sort_by"]
        ai_rerank_enabled = group_cfg["ai_rerank"]

        # 收集这组所有候选
        candidates = []
        for source in sources:
            candidates.extend(source_map.get(source, []))

        if not candidates:
            print(f"  [{group}] 无数据，跳过")
            continue

        # 筛选
        if ai_rerank_enabled:
            selected = ai_rerank(candidates, group, limit)
            print(f"  [{group}] {len(candidates)} 条候选 → AI 精排 → {len(selected)} 条")
        else:
            selected = sorted(candidates, key=lambda x: get_sort_value(x, sort_by), reverse=True)[:limit]
            print(f"  [{group}] {len(candidates)} 条候选 → 按 {sort_by} 取 top {len(selected)} 条")

        for item in selected:
            rows_to_insert.append(build_display_row(item, rank, today))
            rank += 1

    # 批量写入
    if rows_to_insert:
        supabase.table(DISPLAY_TABLE).insert(rows_to_insert).execute()

    total_cost = (datetime.now() - start_time).total_seconds()
    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | 共写入 {len(rows_to_insert)} 条 | {total_cost:.1f}s\n")


if __name__ == "__main__":
    main()
