# scrapers/ai_blogs/anthropic.py

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem

# 与 RSS 保持一致的时间窗口
FETCH_WINDOW_HOURS = 25

# ── 日期正则（按优先级排列）──────────────────────────────────
# 中文/日文：2026年2月23日
_CJK_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 韩文：2026년 2월 23일
_KO_DATE_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

# ISO 格式：2026-02-24
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# 英文缩写月份：Feb 24, 2026 / Feb 24 2026（逗号可选，常与分类文本粘连如 "ProductFeb 17, 2026"）
_EN_SHORT_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s*(\d{1,2}),?\s+(\d{4})"
)

# 英文完整月份：February 24, 2026
_EN_FULL_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})"
)

# 欧式：24 Feb 2026 / 24 February 2026
_EU_DATE_RE = re.compile(
    r"(\d{1,2})\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{4})"
)

# 斜杠/点分隔：2026/02/24, 02/24/2026, 24.02.2026
_SLASH_DATE_RE = re.compile(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})")


def _extract_date_from_text(text: str) -> datetime | None:
    """从文本中提取日期，支持多种语言和格式。"""
    if not text:
        return None

    # 1. 中文/日文 "2026年2月23日"
    m = _CJK_DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass

    # 2. 韩文 "2026년 2월 23일"
    m = _KO_DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass

    # 3. ISO "2026-02-24"
    m = _ISO_DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass

    # 4. 英文完整月份 "February 24, 2026"（先匹配全名，避免缩写截断）
    m = _EN_FULL_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%B %d, %Y")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # 5. 英文缩写月份 "Feb 24, 2026" / 与分类粘连 "ProductFeb 17, 2026"
    m = _EN_SHORT_RE.search(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%b %d, %Y")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # 6. 欧式 "24 Feb 2026" / "24 February 2026"
    m = _EU_DATE_RE.search(text)
    if m:
        try:
            month_str = m.group(2)[:3]  # 截取前3位统一为缩写
            dt = datetime.strptime(f"{month_str} {m.group(1)}, {m.group(3)}", "%b %d, %Y")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # 7. 斜杠/点 "2026/02/24" / "2026.02.24"
    m = _SLASH_DATE_RE.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass

    return None


class AnthropicBlogScraper(BaseScraper):
    source_name = "Anthropic Blog"
    source_type = "BLOG"
    content_type = "article"

    BASE_URL = "https://www.anthropic.com"
    NEWS_URL = "https://www.anthropic.com/news"

    def fetch(self) -> list[RawItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_WINDOW_HOURS)

        try:
            res = requests.get(
                self.NEWS_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            items = []
            seen = set()
            skipped_old = 0

            for card in soup.select("a[href^='/news/']"):
                href = card.get("href", "")
                if not href or href in ("/news", "/news/"):
                    continue
                if href in seen:
                    continue
                seen.add(href)

                full_url = self.BASE_URL + href

                title_tag = card.select_one("h2, h3, h4")
                title = title_tag.get_text(strip=True) if title_tag else card.get_text(strip=True)
                if not title:
                    continue

                desc_tag = card.select_one("p")
                body_text = desc_tag.get_text(strip=True) if desc_tag else ""

                # ── 日期解析：五级 fallback ──
                published_at = None

                # 1. 带日期语义的 CSS class（已知: div.body-3.agate）
                #    也检查其他常见命名模式
                for selector in (
                    "div.body-3.agate", "span.body-3.agate",   # 已确认
                    "[class*='date']", "[class*='Date']",       # 通用
                    "[class*='time']", "[class*='Time']",       # 通用
                    "[class*='publish']", "[class*='Publish']", # 通用
                    "[class*='agate']",                         # 其他 agate 变体
                ):
                    el = card.select_one(selector)
                    if el:
                        published_at = _extract_date_from_text(el.get_text(strip=True))
                        if published_at:
                            break

                # 2. <time> 标签（datetime 属性优先）
                if published_at is None:
                    time_tag = card.select_one("time")
                    if time_tag:
                        dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
                        try:
                            published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        except Exception:
                            published_at = _extract_date_from_text(dt_str)

                # 3. 卡片全文正则匹配（覆盖日期与分类粘连的情况）
                if published_at is None:
                    card_text = card.get_text(" ", strip=True)
                    published_at = _extract_date_from_text(card_text)

                # 4. 向上找父元素 / 相邻兄弟元素中的日期
                if published_at is None:
                    for ancestor in (card.parent, card.find_next_sibling(), card.find_previous_sibling()):
                        if ancestor:
                            published_at = _extract_date_from_text(ancestor.get_text(" ", strip=True))
                            if published_at:
                                break

                # 5. 遍历卡片内所有子元素的短文本
                if published_at is None:
                    for el in card.find_all(["div", "span", "p", "small"]):
                        txt = el.get_text(strip=True)
                        if txt and len(txt) < 40:
                            published_at = _extract_date_from_text(txt)
                            if published_at:
                                break

                # ── 时间过滤 ──
                if published_at is not None and published_at < cutoff:
                    skipped_old += 1
                    continue

                # 无日期的不收录，同时打印警告便于排查
                if published_at is None:
                    print(f"    ⚠️ 无法解析日期，跳过: {title[:50]}")
                    continue

                items.append(RawItem(
                    title=title,
                    original_url=full_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author="Anthropic",
                    author_url=self.BASE_URL,
                    body_text=body_text,
                    raw_metrics={},
                    extra={"source_tag": "official_ai"},
                    published_at=published_at,
                ))

            if skipped_old:
                print(f"  过滤掉 {skipped_old} 条超出时间窗口的旧文章")
            print(f"  抓取到 {len(items)} 条")
            return items

        except Exception as e:
            print(f"⚠️ {self.source_name} 抓取失败: {e}")
            return []