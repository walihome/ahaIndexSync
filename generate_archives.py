"""
AmazingIndex 归档数据生成脚本
==============================

运行时机：在 GitHub Actions 的 rank job 末尾执行
功能：从 display_items 聚合数据，写入 daily_archives / weekly_archives / monthly_archives

用法：
  python generate_archives.py

环境变量：
  SUPABASE_URL      - Supabase 项目 URL
  SUPABASE_KEY      - Supabase service_role key（需要写权限，不要用 anon key）
  KIMI_API_KEY      - kimi-k2.5 API key（可选，用于生成月度摘要）
"""

import os
import datetime
from collections import Counter
from supabase import create_client

# ============================================================
# 初始化
# ============================================================

supabase = create_client(
    os.environ['SUPABASE_URL'],
    os.environ['SUPABASE_KEY']
)

today = datetime.date.today()


# ============================================================
# 工具函数
# ============================================================

def get_weekday_cn(date_str):
    """返回中文星期"""
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    d = datetime.date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    return weekdays[d.weekday()]


def get_week_bounds(date):
    """获取 date 所在周的周一和周日"""
    monday = date - datetime.timedelta(days=date.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


# ============================================================
# 第一步：写入 daily_archives（每天执行）
# ============================================================

def generate_daily_archive(target_date=None):
    """
    从 display_items 聚合指定日期的数据，写入 daily_archives。
    默认处理今天，也可以指定历史日期用于回填。
    """
    target = target_date or today
    target_str = str(target)

    print(f"[daily] 处理 {target_str} ...")

    # 1. 查询当天所有 display_items
    resp = supabase.table('display_items') \
        .select('rank, processed_title, source_name, tags, aha_index, display_metrics') \
        .eq('snapshot_date', target_str) \
        .order('rank') \
        .execute()

    items = resp.data
    if not items:
        print(f"[daily] {target_str} 无数据，跳过")
        return None

    # 2. 取 rank=1 的 top story
    top_item = items[0]

    # 3. 计算当日 aha 总分（所有条目 aha_index 均值 × 100）
    aha_values = [item['aha_index'] for item in items if item.get('aha_index') is not None]
    today_score = round(sum(aha_values) / len(aha_values) * 100, 1) if aha_values else 0

    # 4. 计算 delta（和前一天比较）
    yesterday = target - datetime.timedelta(days=1)
    prev_resp = supabase.table('daily_archives') \
        .select('aha_score') \
        .eq('snapshot_date', str(yesterday)) \
        .execute()

    delta = 0
    if prev_resp.data and prev_resp.data[0].get('aha_score'):
        prev_score = float(prev_resp.data[0]['aha_score'])
        if prev_score > 0:
            delta = round((today_score - prev_score) / prev_score * 100, 1)

    # 5. 聚合 top 3 标签
    all_tags = []
    for item in items:
        if item.get('tags'):
            all_tags.extend(item['tags'])
    top_tags = [tag for tag, _ in Counter(all_tags).most_common(3)]

    # 6. 从 top_item 的 display_metrics 提取维度分数
    #    display_metrics 结构需根据实际情况调整字段名
    metrics = top_item.get('display_metrics') or {}
    rarity = metrics.get('rarity') or metrics.get('rarity_score')
    timeliness = metrics.get('timeliness') or metrics.get('timeliness_score')
    impact = metrics.get('impact') or metrics.get('impact_score')

    # 7. 写入 daily_archives
    row = {
        'snapshot_date': target_str,
        'aha_score': today_score,
        'aha_delta': delta,
        'item_count': len(items),
        'top_story_title': top_item.get('processed_title'),
        'top_story_source': top_item.get('source_name'),
        'top_tags': top_tags,
        'rarity_score': int(rarity) if rarity is not None else None,
        'timeliness_score': int(timeliness) if timeliness is not None else None,
        'impact_score': int(impact) if impact is not None else None,
    }

    supabase.table('daily_archives').upsert(row).execute()
    print(f"[daily] ✓ {target_str} | score={today_score} delta={delta} items={len(items)}")

    return row


# ============================================================
# 第二步：写入 weekly_archives（每周一执行，处理上周）
# ============================================================

def generate_weekly_archive(week_end_date=None):
    """
    从 daily_archives 聚合指定周的数据，写入 weekly_archives。
    默认在周一时处理上一周（周一~周日）。
    也可以指定周日日期用于回填。
    """
    if week_end_date:
        sunday = week_end_date
    else:
        # 如果今天是周一，处理上周
        if today.weekday() != 0:
            print(f"[weekly] 今天不是周一，跳过")
            return None
        sunday = today - datetime.timedelta(days=1)

    monday = sunday - datetime.timedelta(days=6)
    iso_year, iso_week, _ = sunday.isocalendar()

    print(f"[weekly] 处理 {monday} ~ {sunday} (W{iso_week}) ...")

    # 查询这一周的 daily_archives
    resp = supabase.table('daily_archives') \
        .select('*') \
        .gte('snapshot_date', str(monday)) \
        .lte('snapshot_date', str(sunday)) \
        .order('snapshot_date') \
        .execute()

    days = resp.data
    if not days:
        print(f"[weekly] W{iso_week} 无数据，跳过")
        return None

    scores = [float(d['aha_score']) for d in days if d.get('aha_score')]
    peak_day = max(days, key=lambda d: float(d.get('aha_score') or 0))

    row = {
        'year': iso_year,
        'week_number': iso_week,
        'start_date': str(monday),
        'end_date': str(sunday),
        'edition_count': len(days),
        'item_count': sum(d.get('item_count', 0) for d in days),
        'avg_aha_score': round(sum(scores) / len(scores), 1) if scores else 0,
        'peak_aha_score': float(peak_day['aha_score']) if peak_day.get('aha_score') else 0,
        'peak_date': peak_day.get('snapshot_date'),
    }

    # upsert by unique(year, week_number)
    supabase.table('weekly_archives').upsert(
        row, on_conflict='year,week_number'
    ).execute()

    print(f"[weekly] ✓ W{iso_week} | avg={row['avg_aha_score']} peak={row['peak_aha_score']} days={row['edition_count']}")

    return row


# ============================================================
# 第三步：写入 monthly_archives（每月1号执行，处理上月）
# ============================================================

def generate_monthly_summary_text(top_stories, year, month, avg_score):
    """
    调用 kimi-k2.5 生成月度摘要。
    如果 API key 未配置或调用失败，返回 None。
    """
    api_key = os.environ.get('KIMI_API_KEY')
    if not api_key:
        print("[monthly] KIMI_API_KEY 未配置，跳过摘要生成")
        return None

    try:
        import requests
        prompt = f"""你是 AmazingIndex 的编辑。根据以下本月每日 Top Story 标题列表，撰写一段 80-120 字的月度摘要。
要求：
1. 中文撰写，语气客观专业
2. 提及本月 2-3 个最重要的事件/发布
3. 点明行业趋势关键词
4. 最后一句用数据收尾（如"本月Aha Index均值{avg_score}，为近三个月最高"）
5. 不要使用 markdown 格式，直接输出纯文本

月份：{year}年{month}月
Top Story 列表：
{chr(10).join(f"- {s}" for s in top_stories)}
"""

        resp = requests.post(
            'https://api.moonshot.cn/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'moonshot-v1-8k',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"[monthly] 摘要生成失败: {e}")
        return None


def generate_monthly_archive(target_month_start=None):
    """
    从 daily_archives 聚合指定月的数据，写入 monthly_archives。
    默认在每月1号处理上月。
    也可以指定月份首日（如 2026-03-01）用于回填。
    """
    if target_month_start:
        month_start = target_month_start
    else:
        # 如果今天是1号，处理上个月
        if today.day != 1:
            print(f"[monthly] 今天不是1号，跳过")
            return None
        month_start = (today - datetime.timedelta(days=1)).replace(day=1)

    # 计算月末
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    month_end = next_month_start - datetime.timedelta(days=1)

    print(f"[monthly] 处理 {month_start} ~ {month_end} ...")

    # 查询这个月的 daily_archives
    resp = supabase.table('daily_archives') \
        .select('*') \
        .gte('snapshot_date', str(month_start)) \
        .lte('snapshot_date', str(month_end)) \
        .order('snapshot_date') \
        .execute()

    days = resp.data
    if not days:
        print(f"[monthly] {month_start} 无数据，跳过")
        return None

    scores = [float(d['aha_score']) for d in days if d.get('aha_score')]
    peak_day = max(days, key=lambda d: float(d.get('aha_score') or 0))
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # 收集所有 top story 标题用于生成摘要
    top_stories = [d['top_story_title'] for d in days if d.get('top_story_title')]

    # AI 生成月度摘要
    summary = generate_monthly_summary_text(
        top_stories, month_start.year, month_start.month, avg_score
    )

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

    supabase.table('monthly_archives').upsert(row).execute()
    print(f"[monthly] ✓ {month_start} | avg={avg_score} peak={row['peak_aha_score']} editions={row['edition_count']}")

    return row


# ============================================================
# 历史数据回填（首次部署时运行一次）
# ============================================================

def backfill_all():
    """
    回填所有历史数据。从 display_items 中找到最早和最晚的 snapshot_date，
    然后按天 → 按周 → 按月依次生成。

    用法：
      python generate_archives.py --backfill
    """
    print("=" * 60)
    print("开始回填历史数据...")
    print("=" * 60)

    # 1. 找到 display_items 的日期范围
    earliest_resp = supabase.table('display_items') \
        .select('snapshot_date') \
        .order('snapshot_date') \
        .limit(1) \
        .execute()

    latest_resp = supabase.table('display_items') \
        .select('snapshot_date') \
        .order('snapshot_date', desc=True) \
        .limit(1) \
        .execute()

    if not earliest_resp.data or not latest_resp.data:
        print("display_items 表为空，无法回填")
        return

    start_date = datetime.date.fromisoformat(earliest_resp.data[0]['snapshot_date'])
    end_date = datetime.date.fromisoformat(latest_resp.data[0]['snapshot_date'])

    print(f"数据范围: {start_date} ~ {end_date}")

    # 2. 回填 daily_archives（按天遍历）
    print("\n--- 回填 daily_archives ---")
    current = start_date
    daily_count = 0
    while current <= end_date:
        result = generate_daily_archive(current)
        if result:
            daily_count += 1
        current += datetime.timedelta(days=1)
    print(f"daily_archives 完成: {daily_count} 天")

    # 3. 回填 weekly_archives（按周遍历）
    print("\n--- 回填 weekly_archives ---")
    weekly_count = 0
    # 找到 start_date 所在周的周日
    first_sunday = start_date + datetime.timedelta(days=(6 - start_date.weekday()))
    current_sunday = first_sunday
    while current_sunday <= end_date:
        result = generate_weekly_archive(current_sunday)
        if result:
            weekly_count += 1
        current_sunday += datetime.timedelta(days=7)
    print(f"weekly_archives 完成: {weekly_count} 周")

    # 4. 回填 monthly_archives（按月遍历）
    print("\n--- 回填 monthly_archives ---")
    monthly_count = 0
    current_month = start_date.replace(day=1)
    last_month = end_date.replace(day=1)
    while current_month <= last_month:
        result = generate_monthly_archive(current_month)
        if result:
            monthly_count += 1
        # 下一个月
        if current_month.month == 12:
            current_month = current_month.replace(year=current_month.year + 1, month=1)
        else:
            current_month = current_month.replace(month=current_month.month + 1)
    print(f"monthly_archives 完成: {monthly_count} 月")

    print("\n" + "=" * 60)
    print(f"回填完成！daily={daily_count} weekly={weekly_count} monthly={monthly_count}")
    print("=" * 60)


# ============================================================
# 主入口
# ============================================================

def run_daily():
    """
    每天 rank job 末尾调用。
    - 始终生成当天的 daily_archive
    - 如果今天是周一，额外生成上周的 weekly_archive
    - 如果今天是1号，额外生成上月的 monthly_archive
    """
    print(f"=== 归档数据生成 {today} ===")

    # 每天
    generate_daily_archive()

    # 每周一
    if today.weekday() == 0:
        generate_weekly_archive()

    # 每月1号
    if today.day == 1:
        generate_monthly_archive()

    print("=== 完成 ===")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--backfill':
        backfill_all()
    elif len(sys.argv) > 1 and sys.argv[1] == '--date':
        # 手动指定日期: python generate_archives.py --date 2026-03-18
        target = datetime.date.fromisoformat(sys.argv[2])
        generate_daily_archive(target)
    else:
        run_daily()
