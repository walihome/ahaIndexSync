# stages/rank.py

from __future__ import annotations

import os
import json
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import Client
from openai import OpenAI
from pipeline.config_loader import PipelineConfig, RankGroupConfig, TagSlotConfig
from infra.db import table_names
from infra.time_utils import today_str


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


def _fetch_enrichment_map(sb: Client, item_ids: list[str], today: str) -> dict[str, dict[str, dict]]:
    """按 item_id 聚合当天 enrichment：{item_id: {enrichment_type: data}}"""
    if not item_ids:
        return {}
    out: dict[str, dict[str, dict]] = {}
    batch_size = 200
    for i in range(0, len(item_ids), batch_size):
        chunk = item_ids[i:i + batch_size]
        try:
            rows = (
                sb.table("item_enrichments")
                .select("item_id, enrichment_type, data")
                .eq("snapshot_date", today)
                .in_("item_id", chunk)
                .execute()
                .data
                or []
            )
        except Exception as e:
            print(f"  ⚠️ 读取 item_enrichments 失败: {e}")
            rows = []
        for r in rows:
            out.setdefault(r["item_id"], {})[r["enrichment_type"]] = r.get("data") or {}
    return out


def _fetch_subject_history(sb: Client, item_ids: list[str], today: str) -> dict[str, list[dict]]:
    """查今日每条 item 绑定的 subject 及其最近 90 天历史轨迹。返回 item_id → 历史摘要列表。"""
    if not item_ids:
        return {}
    try:
        today_mentions = (
            sb.table("subject_mentions")
            .select("item_id, subject_id")
            .eq("snapshot_date", today)
            .in_("item_id", item_ids)
            .execute()
            .data
            or []
        )
    except Exception as e:
        print(f"  ⚠️ 读取 subject_mentions 失败: {e}")
        return {}

    if not today_mentions:
        return {}

    item_to_subjects: dict[str, list[str]] = {}
    all_subject_ids: set[str] = set()
    for m in today_mentions:
        item_to_subjects.setdefault(m["item_id"], []).append(m["subject_id"])
        all_subject_ids.add(m["subject_id"])

    if not all_subject_ids:
        return {}

    try:
        subjects = (
            sb.table("subjects")
            .select("id, slug, display_name, mention_count, first_seen_at, last_seen_at")
            .in_("id", list(all_subject_ids))
            .execute()
            .data
            or []
        )
    except Exception as e:
        print(f"  ⚠️ 读取 subjects 失败: {e}")
        subjects = []
    subj_map = {s["id"]: s for s in subjects}

    cutoff = (date.fromisoformat(today) - timedelta(days=90)).isoformat()
    try:
        history = (
            sb.table("subject_mentions")
            .select("subject_id, snapshot_date, source_name, score")
            .in_("subject_id", list(all_subject_ids))
            .gte("snapshot_date", cutoff)
            .lt("snapshot_date", today)
            .execute()
            .data
            or []
        )
    except Exception as e:
        print(f"  ⚠️ 读取 subject 历史 mentions 失败: {e}")
        history = []

    hist_map: dict[str, list[dict]] = {}
    for h in history:
        hist_map.setdefault(h["subject_id"], []).append(h)

    out: dict[str, list[dict]] = {}
    for item_id, subject_ids in item_to_subjects.items():
        buckets: list[dict] = []
        for sid in subject_ids:
            s = subj_map.get(sid)
            if not s:
                continue
            hs = hist_map.get(sid, [])
            buckets.append({
                "slug": s["slug"],
                "display_name": s["display_name"],
                "first_seen_at": s.get("first_seen_at"),
                "mention_count": s.get("mention_count") or 0,
                "history": sorted(
                    [{"date": h["snapshot_date"], "source": h.get("source_name"), "score": h.get("score")} for h in hs],
                    key=lambda x: x["date"],
                    reverse=True,
                )[:5],
            })
        if buckets:
            out[item_id] = buckets
    return out


def _format_enrichment_hint(
    enrich_by_type: dict[str, dict],
    subject_history: list[dict],
) -> list[str]:
    """把 enrichment + subject 历史拼成几行 hint。没有就返回空列表。"""
    lines: list[str] = []

    comments = enrich_by_type.get("comments")
    if comments:
        sentiment = comments.get("sentiment")
        debate = comments.get("core_debate")
        if sentiment or debate:
            parts = []
            if sentiment:
                parts.append({"positive": "正面为主", "mixed": "意见分歧", "negative": "负面居多"}.get(sentiment, sentiment))
            if debate:
                parts.append(f"核心争论：{debate}")
            if parts:
                lines.append("社区反馈:" + "，".join(parts))
        alts = comments.get("alternatives") or []
        if alts:
            lines.append(f"评论提到的替代方案:{', '.join(alts[:5])}")

    eco = enrich_by_type.get("ecosystem")
    if eco:
        competitors = eco.get("competitors") or []
        if competitors:
            comp_str = ", ".join(
                f"{c.get('name')}({c.get('stars') or '?'}⭐)"
                for c in competitors[:4]
                if c.get("name")
            )
            position = eco.get("ecosystem_position") or ""
            unique_val = eco.get("unique_value") or ""
            parts = []
            if comp_str:
                parts.append(f"竞品:{comp_str}")
            if position:
                parts.append(position)
            if unique_val:
                parts.append(f"独特价值：{unique_val}")
            if parts:
                lines.append("生态:" + "；".join(parts))
        maturity = eco.get("maturity")
        if maturity:
            lines.append(f"成熟度:{maturity}")

    cross = enrich_by_type.get("cross_reference")
    if cross and cross.get("subject_known"):
        first = cross.get("first_seen_at")
        total = cross.get("total_mention_count") or 0
        hist_cnt = len(cross.get("historical_mentions") or [])
        trend = cross.get("trend")
        bits = []
        if first:
            bits.append(f"首次出现 {first}")
        if total:
            bits.append(f"累计被提及 {total} 次")
        if hist_cnt:
            bits.append(f"近 90 天 {hist_cnt} 次")
        if trend and trend != "new":
            bits.append(f"趋势:{trend}")
        if bits:
            lines.append("历史:" + "，".join(bits))

    if subject_history:
        samples = []
        for s in subject_history[:2]:
            hist = s.get("history") or []
            if hist:
                recent = hist[0]
                samples.append(f"{s['display_name']} 最近见于 {recent['date']}({recent.get('source') or '?'})")
        if samples and not any(l.startswith("历史:") for l in lines):
            lines.append("历史:" + "；".join(samples))

    return lines


def _dedup_by_url(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """保留兼容：如果有人直接调用 run_rank 而未走 coarse_filter。"""
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


def _ai_score(
    candidates: list[dict],
    group: str,
    limit: int,
    config: PipelineConfig,
    api_key: str,
    enrichment_map: dict[str, dict[str, dict]],
    subject_history_map: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
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

    def _candidate_block(i: int, c: dict) -> str:
        item_id = c.get("item_id")
        lines = [
            f"[{i+1}] 来源:{c['source_name']}",
            f"类型:{c.get('content_type','')}",
            f"标题:{c.get('processed_title') or c.get('raw_title')}",
            f"摘要:{c.get('summary','')}",
            f"参考指标:{_fmt(c.get('raw_metrics'))}",
        ]
        enrich = enrichment_map.get(item_id) or {}
        history = subject_history_map.get(item_id) or []
        for hint in _format_enrichment_hint(enrich, history):
            lines.append(hint)
        return "\n".join(lines)

    candidate_text = "\n\n".join(_candidate_block(i, c) for i, c in enumerate(candidates))

    prompt = prompt_cfg.render(
        group=group,
        count=str(len(candidates)),
        idea_guide=idea_cfg.template if idea_cfg else "",
        scoring_guide=scoring_cfg.template if scoring_cfg else "",
        candidate_text=candidate_text,
    )

    system_cfg = config.get_prompt("rank_system")
    client = OpenAI(base_url=prompt_cfg.model_base_url, api_key=api_key)
    temperature = prompt_cfg.temperature
    messages = [
        {"role": "system", "content": system_cfg.template if system_cfg else "You are a JSON-only scorer."},
        {"role": "user", "content": prompt},
    ]

    max_attempts = prompt_cfg.max_retries if hasattr(prompt_cfg, 'max_retries') else 2
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=prompt_cfg.model,
                temperature=temperature,
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
            err_str = str(e)
            if "invalid temperature" in err_str and temperature != 1.0:
                print(f"  ⚠️ 模型不支持 temperature={temperature}，回退到 1.0 重试")
                temperature = 1.0
                continue

            print(f"  ⚠️ AI 打分失败 ({group}): {e}，降级为 aha_index 排序")
            sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
            records = [{"item": item, "ai_score": None, "ai_detail": {"comment": f"异常: {str(e)[:100]}"}, "tags": [], "comment": "", "selected": i < limit} for i, item in enumerate(sorted_items)]
            return sorted_items[:limit], records

    sorted_items = sorted(candidates, key=lambda x: x.get("aha_index", 0), reverse=True)
    records = [{"item": item, "ai_score": None, "ai_detail": {"comment": "重试耗尽"}, "tags": [], "comment": "", "selected": i < limit} for i, item in enumerate(sorted_items)]
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


def run_rank(
    sb: Client,
    config: PipelineConfig,
    table_suffix: str = "",
    candidates: list[dict] | None = None,
) -> dict:
    """
    candidates: 上游 coarse_filter 传入的候选列表。
      - 若为 None，退化为从 processed_items 读取并做基本去重，保证向后兼容。
    """
    _, processed_table, display_table = table_names(table_suffix)
    api_key = os.getenv("KIMI_API_KEY", "")
    today = today_str()

    if candidates is None:
        data = sb.table(processed_table).select("*").eq("snapshot_date", today).execute().data or []
        print(f"📋 今日 processed_items 共 {len(data)} 条（未经粗排）")
        data, dupes = _dedup_by_url(data)
        if dupes:
            print(f"🔀 去重: 去除 {len(dupes)} 条，保留 {len(data)} 条")
    else:
        data = candidates
        print(f"📋 Rank 输入候选 {len(data)} 条")

    if not data:
        print("✅ 无数据，退出")
        return {"display_count": 0}

    item_ids = [d["item_id"] for d in data]
    enrichment_map = _fetch_enrichment_map(sb, item_ids, today)
    subject_history_map = _fetch_subject_history(sb, item_ids, today)
    if enrichment_map or subject_history_map:
        print(f"🧩 enrichment 命中 {len(enrichment_map)} 条，subject 历史 {len(subject_history_map)} 条")

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
        group_candidates = []
        for source in group_cfg.source_names:
            group_candidates.extend(source_map.get(source, []))
        if not group_candidates:
            continue

        print(f"  [{group_cfg.group_name}] {len(group_candidates)} 条候选 → AI 打分:")
        selected, records = _ai_score(
            group_candidates, group_cfg.group_name, group_cfg.limit,
            config, api_key, enrichment_map, subject_history_map,
        )
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
