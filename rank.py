# rank.py
# 精排入口：读 processed_items → 去重 → 链接检查 → 分组打分 → 特殊标签保底 → 写 display_items + 回写 processed_items 审计字段
# 每次运行前先清除当天旧数据，保证幂等可重跑

import os
import json
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from infra.db import supabase, PROCESSED_TABLE, DISPLAY_TABLE
from infra.time_utils import today_str
from infra.link_checker import is_accessible
from config.rank_config import RANK_GROUPS

KIMI_API_KEY = os.getenv("KIMI_API_KEY")
MODEL = "kimi-k2.5"

# 读取 persona 文件
_persona_dir = Path(__file__).parent / "persona"
SCORING_GUIDE = (_persona_dir / "scoring.md").read_text(encoding="utf-8") if (_persona_dir / "scoring.md").exists() else ""
IDEA_GUIDE = (_persona_dir / "idea.md").read_text(encoding="utf-8") if (_persona_dir / "idea.md").exists() else ""

# 特殊标签每日名额
TAG_SLOTS = {"gossip": 1, "deal": 1, "macro": 2, "incident": 1, "lifestyle": 1}


# ── 工具函数 ───────────────────────────────────────────────────

def get_sort_value(item: dict, sort_by: str) -> float:
    metrics = {
        "aha_index": item.get("aha_index", 0),
        **(item.get("raw_metrics") or {}),
    }
    return metrics.get(sort_by, 0) or 0


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


def make_audit_update(
    item_id: str, rank_group: str, rank_action: str,
    rank_score: float = None, rank_detail: dict = None,
) -> tuple[str, dict]:
    """构建回写 processed_items 的审计数据，返回 (item_id, update_dict)"""
    update = {
        "rank_group": rank_group,
        "rank_action": rank_action,
    }
    if rank_score is not None:
        update["rank_score"] = rank_score
    if rank_detail is not None:
        update["rank_detail"] = rank_detail
    return item_id, update


# ── 全局去重 ──────────────────────────────────────────────────

def dedup_by_url(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """按 original_url 去重，保留 aha_index 更高的。返回 (保留, 被去重)"""
    seen: dict[str, dict] = {}
    dupes = []
    for item in data:
        url = item.get("original_url", "")
        if not url:
            continue
        if url in seen:
            existing = seen[url]
            if (item.get("aha_index", 0) or 0) > (existing.get("aha_index", 0) or 0):
                dupes.append(existing)
                seen[url] = item
            else:
                dupes.append(item)
        else:
            seen[url] = item
    return list(seen.values()), dupes


# ── 并发链接检查 ──────────────────────────────────────────────

def check_links_batch(candidates: list[dict], max_workers: int = 10) -> tuple[list[dict], list[dict]]:
    """并发检查链接可访问性。返回 (可访问, 不可访问)"""
    alive, dead = [], []

    def _check(item):
        url = item.get("original_url", "")
        return item, is_accessible(url) if url else True

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check, c): c for c in candidates}
        for future in as_completed(futures):
            try:
                item, ok = future.result()
                (alive if ok else dead).append(item)
            except Exception:
                alive.append(futures[future])

    return alive, dead


# ── AI 多维度打分 ─────────────────────────────────────────────

def ai_score_candidates(candidates: list[dict], group: str, limit: int) -> tuple[list[dict], list[dict]]:
    """
    AI 对候选逐条打分。
    返回 (selected, all_records)
      - selected: 入选的候选列表
      - all_records: 所有候选的打分记录 [{item, ai_score, ai_detail, tags, comment, selected}, ...]
    """
    if not KIMI_API_KEY or not candidates:
        sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
        records = []
        for i, item in enumerate(sorted_items):
            records.append({
                "item": item,
                "ai_score": None,
                "ai_detail": {"comment": "AI 不可用，降级为 aha_index 排序"},
                "tags": [],
                "comment": "AI 不可用，降级为 aha_index 排序",
                "selected": i < limit,
            })
        return sorted_items[:limit], records

    client = OpenAI(base_url="https://api.moonshot.cn/v1", api_key=KIMI_API_KEY)

    candidate_text = "\n\n".join([
        f"[{i+1}] 来源:{c['source_name']}\n"
        f"类型:{c.get('content_type', '')}\n"
        f"标题:{c.get('processed_title') or c.get('raw_title')}\n"
        f"摘要:{c.get('summary', '')}"
        for i, c in enumerate(candidates)
    ])

    prompt = f"""你是 AI 日报编辑，请对以下「{group}」的 {len(candidates)} 条候选内容逐条打分。

## 优先关注的内容方向
{IDEA_GUIDE}

## 评分体系
{SCORING_GUIDE}

## 候选内容
{candidate_text}

请严格按照评分体系中的 5 个正向维度和 2 个扣分项打分，并判断是否需要标记特殊标签（gossip/deal/macro）。

输出 JSON（不要输出任何其他内容）：
{{
  "scores": [
    {{
      "index": 1,
      "actionability": 0,
      "tech_depth": 0,
      "impact": 0,
      "scarcity": 0,
      "audience_fit": 0,
      "marketing_penalty": 0,
      "duplicate_penalty": 0,
      "total": 0,
      "tags": [],
      "comment": "一句话理由"
    }}
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a JSON-only scorer. Output valid JSON and nothing else."},
                {"role": "user", "content": prompt},
            ],
            model=MODEL,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        scores = result.get("scores", [])

        score_map = {}
        for s in scores:
            idx = s.get("index", 0) - 1
            if 0 <= idx < len(candidates):
                score_map[idx] = s

        records = []
        for i, item in enumerate(candidates):
            s = score_map.get(i)
            if s:
                total = (
                    s.get("actionability", 0)
                    + s.get("tech_depth", 0)
                    + s.get("impact", 0)
                    + s.get("scarcity", 0)
                    + s.get("audience_fit", 0)
                    - s.get("marketing_penalty", 0)
                    - s.get("duplicate_penalty", 0)
                )
                detail = {k: s.get(k, 0) for k in [
                    "actionability", "tech_depth", "impact",
                    "scarcity", "audience_fit",
                    "marketing_penalty", "duplicate_penalty",
                ]}
                detail["comment"] = s.get("comment", "")
                records.append({
                    "item": item,
                    "ai_score": total,
                    "ai_detail": detail,
                    "tags": s.get("tags", []),
                    "comment": s.get("comment", ""),
                    "selected": False,
                })
            else:
                records.append({
                    "item": item,
                    "ai_score": item.get("aha_index", 0) * 100,
                    "ai_detail": {"comment": "AI 未返回该条打分，降级为 aha_index"},
                    "tags": [],
                    "comment": "AI 未返回该条打分，降级为 aha_index",
                    "selected": False,
                })

        records.sort(key=lambda r: r["ai_score"] or 0, reverse=True)

        for i in range(min(limit, len(records))):
            records[i]["selected"] = True

        selected = [r["item"] for r in records if r["selected"]]

        for r in records:
            flag = "✅" if r["selected"] else "  "
            title = (r["item"].get("processed_title") or r["item"].get("raw_title", ""))[:40]
            tags_str = f" [{','.join(r['tags'])}]" if r.get("tags") else ""
            print(f"    {flag} {r['ai_score']:5.1f} | {title}{tags_str}")
            if r.get("comment"):
                print(f"         💬 {r['comment']}")

        time.sleep(0.5)
        return selected, records

    except Exception as e:
        print(f"  ⚠️ AI 打分失败 ({group}): {e}，降级为 aha_index 排序")
        sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
        records = []
        for i, item in enumerate(sorted_items):
            records.append({
                "item": item,
                "ai_score": None,
                "ai_detail": {"comment": f"AI 打分异常降级: {str(e)[:100]}"},
                "tags": [],
                "comment": f"AI 打分异常降级: {str(e)[:100]}",
                "selected": i < limit,
            })
        return sorted_items[:limit], records


# ── 特殊标签保底 ──────────────────────────────────────────────

def apply_tag_slots(
    display_rows: list[dict],
    all_ai_records: list[dict],
    today: str,
    min_score: float = 45,
) -> list[dict]:
    """检查特殊标签名额，将遗漏的高分标签内容替换末位。"""
    selected_ids = {r["processed_item_id"] for r in display_rows}

    selected_tags = {}
    for rec in all_ai_records:
        if rec.get("item", {}).get("item_id") in selected_ids:
            for tag in rec.get("tags", []):
                selected_tags[tag] = selected_tags.get(tag, 0) + 1

    for tag, max_slots in TAG_SLOTS.items():
        current_count = selected_tags.get(tag, 0)
        if current_count >= max_slots:
            continue

        tag_candidates = [
            a for a in all_ai_records
            if tag in a.get("tags", [])
            and a.get("item", {}).get("item_id") not in selected_ids
            and (a.get("ai_score") or 0) >= min_score
        ]
        tag_candidates.sort(key=lambda a: a.get("ai_score", 0), reverse=True)

        need = max_slots - current_count
        for tc in tag_candidates[:need]:
            if not display_rows:
                break
            replaced = display_rows.pop()
            item = tc["item"]
            new_row = build_display_row(item, replaced["rank"], today)
            display_rows.append(new_row)
            selected_ids.add(item["item_id"])
            print(f"  🏷️ [{tag}] 保底替换: {item.get('processed_title', '')[:40]} (score={tc.get('ai_score', 0):.1f})")

    return display_rows


# ── 批量回写 processed_items 审计字段 ─────────────────────────

def flush_audit_to_processed(audit_updates: list[tuple[str, dict]]):
    """批量回写 rank_group / rank_action / rank_score / rank_detail 到 processed_items"""
    for item_id, update_data in audit_updates:
        try:
            supabase.table(PROCESSED_TABLE).update(update_data).eq("item_id", item_id).execute()
        except Exception as e:
            print(f"  ⚠️ 回写审计失败 {item_id}: {e}")


# ── 主流程 ─────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    today = today_str()
    print(f"\n🏆 精排启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 读取今日 processed_items
    data = (
        supabase.table(PROCESSED_TABLE)
        .select("*")
        .eq("snapshot_date", today)
        .execute()
        .data
    )
    print(f"📋 今日 processed_items 共 {len(data)} 条")

    if not data:
        print("✅ 无数据，退出")
        return

    # 2. 全局去重
    data, dupes = dedup_by_url(data)
    if dupes:
        print(f"🔀 URL 去重: 去除 {len(dupes)} 条重复，保留 {len(data)} 条")

    # 3. 并发链接检查
    print(f"🔗 链接检查中 ({len(data)} 条)...")
    data, dead_links = check_links_batch(data)
    if dead_links:
        print(f"🔗 链接检查: {len(dead_links)} 条不可访问，保留 {len(data)} 条")

    # 按 source_name 分桶
    source_map: dict[str, list[dict]] = {}
    for item in data:
        source_map.setdefault(item["source_name"], []).append(item)

    # 清除旧 display 数据
    supabase.table(DISPLAY_TABLE).delete().eq("snapshot_date", today).execute()
    print(f"🗑️  已清除今日旧 display 数据\n")

    # 收集审计回写和 AI 打分记录
    audit_updates: list[tuple[str, dict]] = []
    all_ai_records: list[dict] = []  # 用于标签保底

    # 记录去重审计
    for item in dupes:
        audit_updates.append(make_audit_update(
            item["item_id"], "global", "filtered_by_dedup",
            rank_detail={"comment": "URL 重复，保留 aha_index 更高的版本"},
        ))

    # 记录死链审计
    for item in dead_links:
        audit_updates.append(make_audit_update(
            item["item_id"], "global", "filtered_by_link",
            rank_detail={"comment": f"链接不可访问: {item.get('original_url', '')[:80]}"},
        ))

    # 4. 分组循环
    rank = 1
    display_rows = []

    for group_cfg in RANK_GROUPS:
        group = group_cfg["group"]
        sources = group_cfg["sources"]
        limit = group_cfg["limit"]
        sort_by = group_cfg["sort_by"]
        ai_rerank_enabled = group_cfg["ai_rerank"]

        candidates = []
        for source in sources:
            candidates.extend(source_map.get(source, []))

        if not candidates:
            if group_cfg.get("must_include"):
                print(f"  [{group}] ⚠️ must_include=True 但无数据，跳过")
            else:
                print(f"  [{group}] 无数据，跳过")
            continue

        print(f"  [{group}] {len(candidates)} 条候选", end="")

        if ai_rerank_enabled:
            print(f" → AI 打分:")
            selected, score_records = ai_score_candidates(candidates, group, limit)
            all_ai_records.extend(score_records)

            for r in score_records:
                action = "selected" if r["selected"] else "filtered_by_ai"
                audit_updates.append(make_audit_update(
                    r["item"]["item_id"], group, action,
                    rank_score=r.get("ai_score"),
                    rank_detail=r.get("ai_detail"),
                ))

            print(f"    → 入选 {len(selected)} 条")
        else:
            sorted_items = sorted(candidates, key=lambda x: get_sort_value(x, sort_by), reverse=True)
            selected = sorted_items[:limit]
            filtered = sorted_items[limit:]

            print(f" → 按 {sort_by} 取 top {len(selected)} 条")

            for item in selected:
                sv = get_sort_value(item, sort_by)
                audit_updates.append(make_audit_update(
                    item["item_id"], group, "selected",
                    rank_score=sv,
                    rank_detail={"sort_by": sort_by, "comment": f"{sort_by}={sv}"},
                ))
            for item in filtered:
                sv = get_sort_value(item, sort_by)
                audit_updates.append(make_audit_update(
                    item["item_id"], group, "filtered_by_limit",
                    rank_score=sv,
                    rank_detail={"sort_by": sort_by, "comment": f"{sort_by}={sv}，未进入 top {limit}"},
                ))

        for item in selected:
            display_rows.append(build_display_row(item, rank, today))
            rank += 1

    # 5. 特殊标签保底
    if all_ai_records:
        display_rows = apply_tag_slots(display_rows, all_ai_records, today)

    # 6. 写入 display_items
    if display_rows:
        supabase.table(DISPLAY_TABLE).insert(display_rows).execute()

    # 7. 回写 processed_items 审计字段
    print(f"\n📝 回写审计字段 ({len(audit_updates)} 条)...")
    flush_audit_to_processed(audit_updates)

    # 8. 检查 must_include
    missing = [
        g["group"] for g in RANK_GROUPS
        if g.get("must_include") and not any(
            item["source_name"] in g["sources"] for item in data
        )
    ]
    if missing:
        print(f"\n⚠️  以下必要来源今日无数据: {', '.join(missing)}")

    # 9. 统计摘要
    total_cost = (datetime.now() - start_time).total_seconds()
    n_selected = sum(1 for _, u in audit_updates if u.get("rank_action") == "selected")
    n_filtered = len(audit_updates) - n_selected

    print(f"\n{'═' * 50}")
    print(f"✨ 完成 | display: {len(display_rows)} 条 | 审计: 入选 {n_selected} / 淘汰 {n_filtered} | {total_cost:.1f}s")
    print(f"{'═' * 50}\n")


if __name__ == "__main__":
    main()
