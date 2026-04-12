# stages/rank.py

from __future__ import annotations

import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import Client
from openai import OpenAI
from pipeline.config_loader import PipelineConfig, RankGroupConfig, TagSlotConfig
from infra.db import table_names
from infra.time_utils import today_str
from infra.link_checker import is_accessible


def _build_display_row(item: dict, rank: int, today: str) -> dict:
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
        "extra": item.get("extra"),
        "rank": rank,
        "model": item.get("model"),
    }


def _dedup_by_url(data: list[dict]) -> tuple[list[dict], list[dict]]:
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


def _check_links_batch(candidates: list[dict], max_workers: int = 10) -> tuple[list[dict], list[dict]]:
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


def _ai_score(candidates: list[dict], group: str, limit: int, config: PipelineConfig, api_key: str) -> tuple[list[dict], list[dict]]:
    prompt_cfg = config.get_prompt("rank_candidate")
    if not api_key or not candidates or not prompt_cfg:
        sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
        records = [{"item": item, "ai_score": None, "tags": [], "comment": "AI 不可用", "selected": i < limit, "ai_detail": {}} for i, item in enumerate(sorted_items)]
        return sorted_items[:limit], records

    idea_cfg = config.get_prompt("rank_idea")
    scoring_cfg = config.get_prompt("rank_scoring")

    def _fmt(raw) -> str:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return raw
        return json.dumps(raw, ensure_ascii=False) if raw else "{}"

    candidate_text = "\n\n".join([
        f"[{i+1}] 来源:{c['source_name']}\n类型:{c.get('content_type','')}\n标题:{c.get('processed_title') or c.get('raw_title')}\n摘要:{c.get('summary','')}\n参考指标:{_fmt(c.get('raw_metrics'))}"
        for i, c in enumerate(candidates)
    ])

    prompt = prompt_cfg.render(
        group=group,
        count=str(len(candidates)),
        idea_guide=idea_cfg.template if idea_cfg else "",
        scoring_guide=scoring_cfg.template if scoring_cfg else "",
        candidate_text=candidate_text,
    )

    system_cfg = config.get_prompt("rank_system")
    client = OpenAI(base_url=prompt_cfg.model_base_url, api_key=api_key)

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_cfg.template if system_cfg else "You are a JSON-only scorer."},
                {"role": "user", "content": prompt},
            ],
            model=prompt_cfg.model,
            temperature=prompt_cfg.temperature,
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
                total = (s.get("actionability", 0) + s.get("tech_depth", 0) + s.get("impact", 0) + s.get("scarcity", 0) + s.get("audience_fit", 0)
                         - s.get("marketing_penalty", 0) - s.get("duplicate_penalty", 0) - s.get("political_penalty", 0))
                detail = {k: s.get(k, 0) for k in ["actionability", "tech_depth", "impact", "scarcity", "audience_fit", "marketing_penalty", "duplicate_penalty", "political_penalty"]}
                detail["comment"] = s.get("comment", "")
                records.append({"item": item, "ai_score": total, "ai_detail": detail, "tags": s.get("tags", []), "comment": s.get("comment", ""), "selected": False})
            else:
                records.append({"item": item, "ai_score": item.get("aha_index", 0) * 100, "ai_detail": {"comment": "AI 未返回该条打分"}, "tags": [], "comment": "", "selected": False})

        records.sort(key=lambda r: r["ai_score"] or 0, reverse=True)
        for i in range(min(limit, len(records))):
            records[i]["selected"] = True

        selected = [r["item"] for r in records if r["selected"]]
        for r in records:
            flag = "✅" if r["selected"] else "  "
            title = (r["item"].get("processed_title") or r["item"].get("raw_title", ""))[:40]
            tags_str = f" [{','.join(r['tags'])}]" if r.get("tags") else ""
            print(f"    {flag} {r['ai_score']:5.1f} | {title}{tags_str}")

        time.sleep(prompt_cfg.request_interval)
        return selected, records

    except Exception as e:
        print(f"  ⚠️ AI 打分失败 ({group}): {e}，降级为 aha_index 排序")
        sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
        records = [{"item": item, "ai_score": None, "ai_detail": {"comment": f"异常: {str(e)[:100]}"}, "tags": [], "comment": "", "selected": i < limit} for i, item in enumerate(sorted_items)]
        return sorted_items[:limit], records


def _apply_tag_slots(display_rows, all_records, tag_slots: list[TagSlotConfig], today: str) -> list[dict]:
    selected_ids = {r["processed_item_id"] for r in display_rows}
    selected_tags = {}
    for rec in all_records:
        if rec.get("item", {}).get("item_id") in selected_ids:
            for tag in rec.get("tags", []):
                selected_tags[tag] = selected_tags.get(tag, 0) + 1

    for ts in tag_slots:
        current = selected_tags.get(ts.tag_name, 0)
        if current >= ts.max_slots:
            continue
        tag_candidates = [a for a in all_records if ts.tag_name in a.get("tags", []) and a.get("item", {}).get("item_id") not in selected_ids and (a.get("ai_score") or 0) >= ts.min_score]
        tag_candidates.sort(key=lambda a: a.get("ai_score", 0), reverse=True)
        need = ts.max_slots - current
        for tc in tag_candidates[:need]:
            if not display_rows:
                break
            replaced = display_rows.pop()
            item = tc["item"]
            new_row = _build_display_row(item, replaced["rank"], today)
            ai_score = tc.get("ai_score")
            if ai_score is not None:
                new_row["aha_index"] = round(ai_score / 100, 2)
            display_rows.append(new_row)
            selected_ids.add(item["item_id"])
            print(f"  🏷️ [{ts.tag_name}] 保底替换: {item.get('processed_title', '')[:40]}")
    return display_rows


def run_rank(sb: Client, config: PipelineConfig, table_suffix: str = "") -> dict:
    _, processed_table, display_table = table_names(table_suffix)
    api_key = os.getenv("KIMI_API_KEY", "")
    link_workers = int(config.get_param("link_check_max_workers", 10))
    today = today_str()

    data = sb.table(processed_table).select("*").eq("snapshot_date", today).execute().data
    print(f"📋 今日 processed_items 共 {len(data)} 条")
    if not data:
        print("✅ 无数据，退出")
        return {"display_count": 0}

    data, dupes = _dedup_by_url(data)
    if dupes:
        print(f"🔀 去重: 去除 {len(dupes)} 条，保留 {len(data)} 条")

    print(f"🔗 链接检查中 ({len(data)} 条)...")
    data, dead_links = _check_links_batch(data, link_workers)
    if dead_links:
        print(f"🔗 死链: {len(dead_links)} 条，保留 {len(data)} 条")

    source_map: dict[str, list[dict]] = {}
    for item in data:
        source_map.setdefault(item["source_name"], []).append(item)

    sb.table(display_table).delete().eq("snapshot_date", today).execute()
    print(f"🗑️ 已清除今日旧 display 数据\n")

    all_records = []
    audit_updates = []
    rank = 1
    display_rows = []

    for group_cfg in config.rank_groups:
        candidates = []
        for source in group_cfg.source_names:
            candidates.extend(source_map.get(source, []))
        if not candidates:
            continue

        print(f"  [{group_cfg.group_name}] {len(candidates)} 条候选 → AI 打分:")
        selected, records = _ai_score(candidates, group_cfg.group_name, group_cfg.limit, config, api_key)
        all_records.extend(records)

        for r in records:
            action = "selected" if r["selected"] else "filtered_by_ai"
            audit_updates.append((r["item"]["item_id"], {"rank_group": group_cfg.group_name, "rank_action": action, "rank_score": r.get("ai_score"), "rank_detail": r.get("ai_detail")}))

        score_by_id = {r["item"]["item_id"]: r.get("ai_score", 0) for r in records}
        for item in selected:
            row = _build_display_row(item, rank, today)
            ai_score = score_by_id.get(item["item_id"])
            if ai_score is not None:
                row["aha_index"] = round(ai_score / 100, 2)
            display_rows.append(row)
            rank += 1

    if all_records and config.tag_slots:
        display_rows = _apply_tag_slots(display_rows, all_records, config.tag_slots, today)

    if display_rows:
        sb.table(display_table).insert(display_rows).execute()

    for item_id, update_data in audit_updates:
        try:
            sb.table(processed_table).update(update_data).eq("item_id", item_id).execute()
        except Exception as e:
            print(f"  ⚠️ 回写审计失败 {item_id}: {e}")

    print(f"\n📊 Rank 完成: display {len(display_rows)} 条")
    return {"display_count": len(display_rows)}
