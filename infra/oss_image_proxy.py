"""
层级二：面向业务的图片代理能力
"""

import os
import re
import hashlib
from datetime import datetime

import requests

from infra.oss_client import put_bytes, exists


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

_DEFAULT_PREFIX = "image"
_TIMEOUT = 30
_USER_AGENT = "AhaIndex-ImageProxy/1.0"

_OSS_DOMAIN = "amazingindex.oss-cn-hangzhou.aliyuncs.com"
_CDN_DOMAIN = "www.amazingindex.com"


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _to_cdn_url(oss_url: str) -> str:
    """把 OSS 直连域名替换为 CDN 域名"""
    return oss_url.replace(_OSS_DOMAIN, _CDN_DOMAIN)


def _download(url: str) -> tuple[bytes, str]:
    resp = requests.get(
        url,
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()

    ct = resp.headers.get("Content-Type", "")
    if "svg" in ct:
        content_type = "image/svg+xml"
        ext = ".svg"
    elif "png" in ct:
        content_type = "image/png"
        ext = ".png"
    elif "gif" in ct:
        content_type = "image/gif"
        ext = ".gif"
    elif "webp" in ct:
        content_type = "image/webp"
        ext = ".webp"
    else:
        content_type = "image/jpeg"
        ext = ".jpg"

    return resp.content, content_type, ext


def _md5_short(s: str, length: int = 8) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:length]


def _make_object_key(prefix: str, sub_dir: str, filename: str, date_str: str | None = None) -> str:
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    return f"{prefix}/{date_str}/{sub_dir}/{filename}"


# ---------------------------------------------------------------------------
# 公开 API - GitHub 图片代理
# ---------------------------------------------------------------------------

def proxy_github_image(
    image_url: str,
    owner: str | None = None,
    repo: str | None = None,
    prefix: str = _DEFAULT_PREFIX,
    date_str: str | None = None,
    skip_exists: bool = True,
    **oss_kwargs,
) -> str:
    content, content_type, ext = _download(image_url)

    url_hash = _md5_short(image_url)
    if owner and repo:
        filename = f"{owner}-{repo}-{url_hash}{ext}"
    else:
        filename = f"img-{url_hash}{ext}"

    object_key = _make_object_key(prefix, "github", filename, date_str)

    if skip_exists and exists(object_key, **oss_kwargs):
        print(f"⏭️  已存在，跳过: {object_key}")
        from infra.oss_client import _get_bucket, _build_public_url
        bucket = _get_bucket(**oss_kwargs)
        return _to_cdn_url(_build_public_url(bucket, object_key))

    oss_url = put_bytes(content, object_key, content_type, **oss_kwargs)
    cdn_url = _to_cdn_url(oss_url)
    print(f"✅ [GitHub Image] {image_url[:60]}... → {cdn_url}")
    return cdn_url


def proxy_github_images(
    image_urls: list[str],
    owner: str | None = None,
    repo: str | None = None,
    **kwargs,
) -> list[str]:
    results = []
    for url in image_urls:
        try:
            cdn_url = proxy_github_image(url, owner, repo, **kwargs)
            results.append(cdn_url)
        except Exception as e:
            print(f"⚠️ 代理失败，保留原链接: {url} ({e})")
            results.append(url)
    return results


# ---------------------------------------------------------------------------
# 公开 API - Star History 代理
# ---------------------------------------------------------------------------

def proxy_star_history(
    repo_full_name: str,
    theme: str = "light",
    prefix: str = _DEFAULT_PREFIX,
    date_str: str | None = None,
    skip_exists: bool = True,
    **oss_kwargs,
) -> str:
    safe_name = repo_full_name.replace("/", "-")
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    object_key = _make_object_key(prefix, "star-history", f"{safe_name}.svg", date_str)

    if skip_exists and exists(object_key, **oss_kwargs):
        print(f"⏭️  已存在，跳过: {object_key}")
        from infra.oss_client import _get_bucket, _build_public_url
        bucket = _get_bucket(**oss_kwargs)
        return _to_cdn_url(_build_public_url(bucket, object_key))

    params = {"repos": repo_full_name, "type": "Date"}
    if theme == "dark":
        params["theme"] = "dark"

    resp = requests.get(
        "https://api.star-history.com/svg",
        params=params,
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()

    oss_url = put_bytes(resp.content, object_key, "image/svg+xml", **oss_kwargs)
    cdn_url = _to_cdn_url(oss_url)
    print(f"✅ [Star History] {repo_full_name} → {cdn_url}")
    return cdn_url