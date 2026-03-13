# infra/link_checker.py
# 校验链接是否可访问
# 核心原则：宁可放过死链，也不误杀正常链接
#
# 过滤规则：
#   明确不可访问 → 过滤（404、410、连接失败、超时）
#   不确定        → 放行（403、405、503 等，可能是反爬）
#   明确可访问    → 放行（200-399）

import requests

TIMEOUT = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 明确表示资源不存在，可以安全过滤
DEFINITE_DEAD_CODES = {404, 410}

# 不确定，可能是反爬/权限问题，保守放行
UNCERTAIN_CODES = {401, 403, 405, 406, 429, 500, 502, 503, 504}


def is_accessible(url: str) -> bool:
    """
    检查链接是否可访问。
    返回 True  → 放行展示
    返回 False → 过滤（仅在明确确认不可访问时）
    """
    try:
        # 先用 HEAD，省带宽
        resp = requests.head(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers=HEADERS,
        )
        status = resp.status_code

        if status in DEFINITE_DEAD_CODES:
            return False

        if status in UNCERTAIN_CODES:
            # HEAD 不确定，改用 GET 再确认一次
            return _fallback_get(url)

        # 200-399 直接放行
        return True

    except requests.exceptions.ConnectionError:
        # 域名无法解析、连接被拒绝 → 明确死链
        return False
    except requests.exceptions.Timeout:
        # 超时 → 过滤
        return False
    except Exception:
        # 其他未知异常 → 保守放行，不误杀
        return True


def _fallback_get(url: str) -> bool:
    """HEAD 返回不确定状态码时，用 GET 再确认"""
    try:
        resp = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers=HEADERS,
            stream=True,  # 只取响应头，不下载 body
        )
        resp.close()
        status = resp.status_code

        if status in DEFINITE_DEAD_CODES:
            return False

        # GET 也返回不确定状态码 → 保守放行
        return True

    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False
    except Exception:
        return True
