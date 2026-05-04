# stages/archive.py

from __future__ import annotations

import os
import datetime
from collections import Counter

import requests
from supabase import Client
from pipeline.config_loader import PipelineConfig
from infra.time_utils import get_today_str


def run_archive(sb: Client, config: PipelineConfig) -> dict:
    today = datetime.date.fromisoformat(get_today_str())
    print(f"=== 归档数据生成 {today} ===")

    daily = _generate_daily(sb, today)
    weekly = None
    monthly = None

    if today.weekday() == 0:
        weekly = _generate_weekly(sb, today)
    if today.day == 1:
        monthly = _generate_monthly(sb, today, config)

    print("=== 归档完成 ===")
    return {"daily": 1 if daily else 0, "weekly": 1 if weekly else 0, "monthly": 1 if monthly else 0}


def _generate_daily(sb: Client, target: datetime.date) -> dict | None:
    target_str = str(target)
    resp = sb.table('display_items').select('rank, processed_title, source_name, tags, aha_index, display_metrics').eq('snapshot_date', target_str).order('rank').execute()
    items = resp.data
    if not items:
        print(f"[daily] {target_str} 无数据，跳过")
        return None

    top_item = items[0]
    aha_values = [item['aha_index'] for item in items if item.get('aha_index') is not None]
    today_score = round(sum(aha_values) / len(aha_values) * 100, 1) if aha_values else 0

    yesterday = target - datetime.timedelta(days=1)
    prev_resp = sb.table('daily_archives').select('aha_score').eq('snapshot_date', str(yesterday)).execute()
    delta = 0
    if prev_resp.data and prev_resp.data[0].get('aha_score'):
        prev_score = float(prev_resp.data[0]['aha_score'])
        if prev_score > 0:
            delta = round((today_score - prev_score) / prev_score * 100, 1)

    all_tags = []
    for item in items:
        if item.get('tags'):
            all_tags.extend(item['tags'])
    top_tags = [tag for tag, _ in Counter(all_tags).most_common(3)]

    metrics = top_item.get('display_metrics') or {}

    # ── 分位数计算（近 90 天窗口）──
    window_start = target - datetime.timedelta(days=90)
    hist_resp = sb.table('daily_archives').select('snapshot_date, aha_score').gte('snapshot_date', str(window_start)).lt('snapshot_date', target_str).execute()
    hist_scores = [float(d['aha_score']) for d in (hist_resp.data or []) if d.get('aha_score') is not None]
    sample_size = len(hist_scores)

    if sample_size < 30:
        percentile_90d = None
        percentile_tier = 'insufficient_data'
    else:
        count_below = sum(1 for s in hist_scores if s < today_score)
        percentile_90d = round(count_below / sample_size, 2)
        if percentile_90d >= 0.90:
            percentile_tier = 'p90_plus'
        elif percentile_90d >= 0.70:
            percentile_tier = 'p70_p90'
        else:
            percentile_tier = 'below_p70'

    row = {
        'snapshot_date': target_str,
        'aha_score': today_score,
        'aha_delta': delta,
        'item_count': len(items),
        'top_story_title': top_item.get('processed_title'),
        'top_story_source': top_item.get('source_name'),
        'top_tags': top_tags,
        'rarity_score': int(v) if (v := metrics.get('rarity') or metrics.get('rarity_score')) is not None else None,
        'timeliness_score': int(v) if (v := metrics.get('timeliness') or metrics.get('timeliness_score')) is not None else None,
        'impact_score': int(v) if (v := metrics.get('impact') or metrics.get('impact_score')) is not None else None,
        'percentile_90d': percentile_90d,
        'percentile_tier': percentile_tier,
        'sample_size_90d': sample_size,
    }
    sb.table('daily_archives').upsert(row).execute()
    print(f"[daily] ✓ {target_str} | score={today_score} items={len(items)} | p90d={percentile_90d} tier={percentile_tier} sample={sample_size}")
    return row


def _generate_weekly(sb: Client, today: datetime.date) -> dict | None:
    sunday = today - datetime.timedelta(days=1)
    monday = sunday - datetime.timedelta(days=6)
    iso_year, iso_week, _ = sunday.isocalendar()

    resp = sb.table('daily_archives').select('*').gte('snapshot_date', str(monday)).lte('snapshot_date', str(sunday)).order('snapshot_date').execute()
    days = resp.data
    if not days:
        return None

    scores = [float(d['aha_score']) for d in days if d.get('aha_score')]
    peak_day = max(days, key=lambda d: float(d.get('aha_score') or 0))
    row = {
        'year': iso_year, 'week_number': iso_week,
        'start_date': str(monday), 'end_date': str(sunday),
        'edition_count': len(days),
        'item_count': sum(d.get('item_count', 0) for d in days),
        'avg_aha_score': round(sum(scores) / len(scores), 1) if scores else 0,
        'peak_aha_score': float(peak_day['aha_score']) if peak_day.get('aha_score') else 0,
        'peak_date': peak_day.get('snapshot_date'),
    }
    sb.table('weekly_archives').upsert(row, on_conflict='year,week_number').execute()
    print(f"[weekly] ✓ W{iso_week}")
    return row


def _generate_monthly(sb: Client, today: datetime.date, config: PipelineConfig) -> dict | None:
    month_start = (today - datetime.timedelta(days=1)).replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    month_end = next_month - datetime.timedelta(days=1)

    resp = sb.table('daily_archives').select('*').gte('snapshot_date', str(month_start)).lte('snapshot_date', str(month_end)).order('snapshot_date').execute()
    days = resp.data
    if not days:
        return None

    scores = [float(d['aha_score']) for d in days if d.get('aha_score')]
    peak_day = max(days, key=lambda d: float(d.get('aha_score') or 0))
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    top_stories = [d['top_story_title'] for d in days if d.get('top_story_title')]

    summary = _generate_summary(top_stories, month_start.year, month_start.month, avg_score, config)

    row = {
        'month': str(month_start),
        'edition_count': len(days),
        'item_count': sum(d.get('item_count', 0) for d in days),
        'avg_aha_score': avg_score,
        'peak_aha_score': float(peak_day['aha_score']) if peak_day.get('aha_score') else 0,
        'peak_date': peak_day.get('snapshot_date'),
        'summary': summary,
        'meta_description': summary[:150] if summary else None,
    }
    sb.table('monthly_archives').upsert(row).execute()
    print(f"[monthly] ✓ {month_start}")
    return row


def _generate_summary(top_stories: list[str], year: int, month: int, avg_score: float, config: PipelineConfig) -> str | None:
    api_key = os.environ.get('KIMI_API_KEY')
    if not api_key:
        return None

    prompt_cfg = config.get_prompt("archive_monthly_summary")
    if not prompt_cfg:
        return None

    prompt = prompt_cfg.render(
        year=str(year),
        month=str(month),
        avg_score=str(avg_score),
        top_stories="\n".join(f"- {s}" for s in top_stories),
    )

    try:
        resp = requests.post(
            f"{prompt_cfg.model_base_url}/chat/completions",
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': prompt_cfg.model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': prompt_cfg.temperature},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"[monthly] 摘要生成失败: {e}")
        return None
