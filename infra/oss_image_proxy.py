"""
层级二：面向业务的图片代理能力

把外部图片链接（GitHub / star-history）拉取后上传 OSS，
返回稳定可控的阿里云 URL，解决外链不稳定 / 加载慢 / 被墙等问题。

依赖: pip install requests
依赖: infra.oss_client (层级一)
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

_DEFAULT_PREFIX = "test"              # OSS 路径前缀
_TIMEOUT = 30                         # HTTP 下载超时
_USER_AGENT = "AhaIndex-ImageProxy/1.0"


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _download(url: str) -> tuple[bytes, str]:
    """
    下载 URL，返回 (content_bytes, guessed_content_type)。
    """
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
    """
    拼 OSS object key: {prefix}/{date}/{sub_dir}/{filename}
    例: test/20260322/github/langchain-ai-langchain-a1b2c3d4.jpg
    """
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
    """
    入参: GitHub 图片 URL（README 里提取的）
    出参: 阿里云 OSS URL

    Args:
        image_url:    原始图片链接
        owner:        仓库 owner（用于文件命名，可选）
        repo:         仓库名（用于文件命名，可选）
        prefix:       OSS 前缀
        date_str:     日期目录
        skip_exists:  如果 OSS 已存在则跳过
        **oss_kwargs: 透传给 oss_client

    Returns:
        OSS 公开 URL
    """
    content, content_type, ext = _download(image_url)

    # 文件名: owner-repo-{url_hash}.ext 或 img-{url_hash}.ext
    url_hash = _md5_short(image_url)
    if owner and repo:
        filename = f"{owner}-{repo}-{url_hash}{ext}"
    else:
        filename = f"img-{url_hash}{ext}"

    object_key = _make_object_key(prefix, "github", filename, date_str)

    if skip_exists and exists(object_key, **oss_kwargs):
        print(f"⏭️  已存在，跳过: {object_key}")
        # 还是要返回 URL
        from infra.oss_client import _get_bucket, _build_public_url
        bucket = _get_bucket(**oss_kwargs)
        return _build_public_url(bucket, object_key)

    oss_url = put_bytes(content, object_key, content_type, **oss_kwargs)
    print(f"✅ [GitHub Image] {image_url[:60]}... → {oss_url}")
    return oss_url


def proxy_github_images(
    image_urls: list[str],
    owner: str | None = None,
    repo: str | None = None,
    **kwargs,
) -> list[str]:
    """
    批量代理 GitHub 图片，返回 OSS URL 列表（顺序对应）。
    单张失败不影响其他，失败的保留原始 URL。
    """
    results = []
    for url in image_urls:
        try:
            oss_url = proxy_github_image(url, owner, repo, **kwargs)
            results.append(oss_url)
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
    """
    入参: GitHub 仓库全名（如 "langchain-ai/langchain"）
    出参: 阿里云 OSS URL（star-history SVG）

    Args:
        repo_full_name: "owner/repo"
        theme:          "light" / "dark"
        prefix:         OSS 前缀
        date_str:       日期目录
        skip_exists:    如果 OSS 已存在则跳过
        **oss_kwargs:   透传给 oss_client

    Returns:
        OSS 公开 URL

    示例:
        url = proxy_star_history("langchain-ai/langchain")
        # → https://dooocs.oss-cn-hangzhou.aliyuncs.com/test/20260322/star-history/langchain-ai-langchain.svg
    """
    safe_name = repo_full_name.replace("/", "-")
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    object_key = _make_object_key(prefix, "star-history", f"{safe_name}.svg", date_str)

    if skip_exists and exists(object_key, **oss_kwargs):
        print(f"⏭️  已存在，跳过: {object_key}")
        from infra.oss_client import _get_bucket, _build_public_url
        bucket = _get_bucket(**oss_kwargs)
        return _build_public_url(bucket, object_key)

    # 拉取 star-history SVG
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
    print(f"✅ [Star History] {repo_full_name} → {oss_url}")
    return oss_url
