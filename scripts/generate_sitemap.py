"""
生成 sitemap.xml 和 robots.txt 并上传到 OSS。
在 export_oss.py 之后运行，确保包含当天新数据。

用法:
    python scripts/generate_sitemap.py
"""

import os
import json
import oss2

SITE_URL = 'https://www.amazingindex.com'
OSS_ENDPOINT = os.environ.get('OSS_ENDPOINT', 'oss-cn-hangzhou.aliyuncs.com')
OSS_BUCKET = os.environ.get('OSS_BUCKET', 'amazingindex')
OSS_AK_ID = os.environ.get('OSS_ACCESS_KEY_ID')
OSS_AK_SECRET = os.environ.get('OSS_ACCESS_KEY_SECRET')


def main():
    if not all([OSS_AK_ID, OSS_AK_SECRET]):
        print("❌ OSS credentials not found in environment variables.")
        return

    auth = oss2.Auth(OSS_AK_ID, OSS_AK_SECRET)
    bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)

    # 1. 从 OSS 读取所有日期和文章
    print("📖 Reading daily data from OSS...")
    daily_data = {}
    for obj in oss2.ObjectIterator(bucket, prefix='api/daily/'):
        if not obj.key.endswith('.json'):
            continue
        date_str = obj.key.split('/')[-1].replace('.json', '')
        try:
            result = bucket.get_object(obj.key)
            data = json.loads(result.read())
            daily_data[date_str] = data.get('items', [])
        except Exception as e:
            print(f"  ⚠️ Skip {obj.key}: {e}")

    total_articles = sum(len(v) for v in daily_data.values())
    print(f"📦 Found {len(daily_data)} days, {total_articles} articles")

    # 2. 生成 URL 列表
    urls = []

    # 首页
    urls.append(make_url(f'{SITE_URL}/', changefreq='daily', priority='1.0'))

    # 归档总览页
    urls.append(make_url(f'{SITE_URL}/daily', changefreq='daily', priority='0.9'))

    months_added = set()

    for date in sorted(daily_data.keys(), reverse=True):
        items = daily_data[date]

        # 日期页
        urls.append(make_url(
            f'{SITE_URL}/daily/{date}',
            lastmod=date, changefreq='never', priority='0.7'
        ))

        # 文章页
        for item in items:
            pid = item.get('processed_item_id', '')
            if not pid:
                continue
            urls.append(make_url(
                f'{SITE_URL}/daily/{date}/article/{pid}',
                lastmod=date, changefreq='never', priority='0.6'
            ))

        # 月份页（去重）
        month = date[:7]
        if month not in months_added:
            months_added.add(month)
            urls.append(make_url(
                f'{SITE_URL}/daily/{month}',
                changefreq='daily', priority='0.8'
            ))

    # 静态页面
    static_pages = [
        ('history', '0.5'),
        ('about', '0.3'),
        ('contact', '0.3'),
        ('privacy', '0.2'),
        ('terms', '0.2'),
    ]
    for page, pri in static_pages:
        urls.append(make_url(f'{SITE_URL}/{page}', changefreq='monthly', priority=pri))

    # 3. 组装 sitemap XML
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    # 4. 上传 sitemap.xml
    bucket.put_object(
        'sitemap.xml', sitemap,
        headers={'Content-Type': 'application/xml; charset=utf-8'}
    )
    print(f"✅ sitemap.xml uploaded ({len(urls)} URLs)")

    # 5. 上传 robots.txt
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    bucket.put_object(
        'robots.txt', robots,
        headers={'Content-Type': 'text/plain; charset=utf-8'}
    )
    print("✅ robots.txt uploaded")

    # 6. 输出统计
    print(f"\n📊 Summary:")
    print(f"   Days:     {len(daily_data)}")
    print(f"   Articles: {total_articles}")
    print(f"   Months:   {len(months_added)}")
    print(f"   Total URLs: {len(urls)}")


def make_url(loc, lastmod=None, changefreq=None, priority=None):
    """生成单条 <url> XML"""
    parts = [f'    <loc>{loc}</loc>']
    if lastmod:
        parts.append(f'    <lastmod>{lastmod}</lastmod>')
    if changefreq:
        parts.append(f'    <changefreq>{changefreq}</changefreq>')
    if priority:
        parts.append(f'    <priority>{priority}</priority>')
    return f"  <url>\n{chr(10).join(parts)}\n  </url>"


if __name__ == '__main__':
    main()