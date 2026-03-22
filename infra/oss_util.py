"""
阿里云 OSS 上传工具 + Star History 图片获取

基础能力模块，供 pipeline 各阶段复用。

依赖: pip install oss2 requests

环境变量:
    OSS_ACCESS_KEY_ID
    OSS_ACCESS_KEY_SECRET
    OSS_BUCKET        (默认: dooocs)
    OSS_ENDPOINT       (默认: oss-cn-hangzhou.aliyuncs.com)
"""

import os
from datetime import datetime

import oss2
import requests


# ---------------------------------------------------------------------------
# OSS 基础能力
# ---------------------------------------------------------------------------

def get_oss_bucket(
    bucket_name: str | None = None,
    endpoint: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> oss2.Bucket:
    """获取 OSS Bucket 实例，参数优先从入参取，fallback 到环境变量。"""
    ak = access_key_id or os.environ["OSS_ACCESS_KEY_ID"]
    sk = access_key_secret or os.environ["OSS_ACCESS_KEY_SECRET"]
    bucket = bucket_name or os.getenv("OSS_BUCKET", "dooocs")
    ep = endpoint or os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")

    auth = oss2.Auth(ak, sk)
    return oss2.Bucket(auth, f"https://{ep}", bucket)


def upload_bytes(
    content: bytes,
    object_key: str,
    content_type: str = "application/octet-stream",
    **oss_kwargs,
) -> str:
    """
    上传 bytes 到 OSS，返回公开访问 URL。

    Args:
        content: 文件内容
        object_key: OSS 上的路径, 如 "test/20260322/owner-repo.svg"
        content_type: MIME 类型
        **oss_kwargs: 透传给 get_oss_bucket 的参数

    Returns:
        公开访问 URL
    """
    bucket = get_oss_bucket(**oss_kwargs)
    headers = {"Content-Type": content_type}
    bucket.put_object(object_key, content, headers=headers)

    ep_host = bucket.endpoint.replace("https://", "").replace("http://", "")
    return f"https://{bucket.bucket_name}.{ep_host}/{object_key}"


def upload_file(
    file_path: str,
    object_key: str,
    content_type: str | None = None,
    **oss_kwargs,
) -> str:
    """上传本地文件到 OSS，返回公开访问 URL。"""
    with open(file_path, "rb") as f:
        data = f.read()

    if content_type is None:
        ext = os.path.splitext(file_path)[1].lower()
        content_type = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".json": "application/json",
        }.get(ext, "application/octet-stream")

    return upload_bytes(data, object_key, content_type, **oss_kwargs)


# ---------------------------------------------------------------------------
# Star History 能力
# ---------------------------------------------------------------------------

def fetch_star_history_svg(repo: str, theme: str = "light") -> bytes:
    """
    拉取某个 GitHub 仓库的 star-history SVG 图。

    Args:
        repo: 如 "langchain-ai/langchain"
        theme: "light" 或 "dark"

    Returns:
        SVG 文件的 bytes
    """
    params = {"repos": repo, "type": "Date"}
    if theme == "dark":
        params["theme"] = "dark"

    resp = requests.get(
        "https://api.star-history.com/svg",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


def upload_star_history(
    repo: str,
    prefix: str = "test",
    theme: str = "light",
    date_str: str | None = None,
    **oss_kwargs,
) -> str:
    """
    一步到位: 拉取 star-history SVG → 上传 OSS → 返回链接。

    Args:
        repo: GitHub 仓库，如 "langchain-ai/langchain"
        prefix: OSS 路径前缀，如 "test"
        theme: "light" / "dark"
        date_str: 日期目录名，默认当天 YYYYMMDD
        **oss_kwargs: 透传给 get_oss_bucket

    Returns:
        OSS 公开访问 URL

    示例:
        url = upload_star_history("langchain-ai/langchain")
        # → https://dooocs.oss-cn-hangzhou.aliyuncs.com/test/20260322/langchain-ai-langchain.svg
    """
    svg_bytes = fetch_star_history_svg(repo, theme)

    date_str = date_str or datetime.now().strftime("%Y%m%d")
    safe_name = repo.replace("/", "-")
    object_key = f"{prefix}/{date_str}/{safe_name}.svg"

    url = upload_bytes(svg_bytes, object_key, "image/svg+xml", **oss_kwargs)
    print(f"✅ [{repo}] → {url}")
    return url


# ---------------------------------------------------------------------------
# 直接运行 / 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 快速测试：python infra/oss_utils.py owner/repo1 owner/repo2
    import sys

    repos = sys.argv[1:] or ["langchain-ai/langchain"]
    for r in repos:
        upload_star_history(r)
