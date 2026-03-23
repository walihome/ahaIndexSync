"""
层级一：阿里云 OSS 基础读写能力

纯基础设施，不含任何业务逻辑，任何上游业务都可以复用。

依赖: pip install oss2
环境变量:
    OSS_ACCESS_KEY_ID
    OSS_ACCESS_KEY_SECRET
    OSS_BUCKET    (默认: dooocs)
    OSS_ENDPOINT  (默认: oss-cn-hangzhou.aliyuncs.com)
"""

import os
import mimetypes
from urllib.parse import quote

import oss2


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _get_bucket(
    bucket_name: str | None = None,
    endpoint: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> oss2.Bucket:
    """构建 OSS Bucket 实例，参数优先入参，fallback 环境变量。"""
    ak = access_key_id or os.environ["OSS_ACCESS_KEY_ID"]
    sk = access_key_secret or os.environ["OSS_ACCESS_KEY_SECRET"]
    bkt = bucket_name or os.getenv("OSS_BUCKET", "dooocs")
    ep = endpoint or os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    if not ep.startswith("http"):
        ep = f"https://{ep}"
    return oss2.Bucket(oss2.Auth(ak, sk), ep, bkt)


def _build_public_url(bucket: oss2.Bucket, object_key: str) -> str:
    """拼接公开访问 URL。"""
    host = bucket.endpoint.replace("https://", "").replace("http://", "")
    # 对 object_key 中的路径做 URL 编码，但保留 /
    safe_key = "/".join(quote(seg, safe="") for seg in object_key.split("/"))
    return f"https://{bucket.bucket_name}.{host}/{safe_key}"


def _guess_content_type(filename: str) -> str:
    ct, _ = mimetypes.guess_type(filename)
    return ct or "application/octet-stream"


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def put_bytes(
    content: bytes,
    object_key: str,
    content_type: str | None = None,
    **oss_kwargs,
) -> str:
    """
    上传 bytes → OSS，返回公开 URL。

    Args:
        content:      文件内容
        object_key:   OSS 路径，如 "test/20260322/foo.svg"
        content_type: MIME，默认按扩展名猜
        **oss_kwargs:  透传 bucket_name / endpoint / access_key_id / access_key_secret

    Returns:
        公开访问 URL
    """
    bucket = _get_bucket(**oss_kwargs)
    ct = content_type or _guess_content_type(object_key)
    bucket.put_object(object_key, content, headers={"Content-Type": ct})
    return _build_public_url(bucket, object_key)


def put_file(file_path: str, object_key: str, **oss_kwargs) -> str:
    """上传本地文件 → OSS，返回公开 URL。"""
    with open(file_path, "rb") as f:
        return put_bytes(f.read(), object_key, **oss_kwargs)


def get_bytes(object_key: str, **oss_kwargs) -> bytes:
    """从 OSS 下载，返回 bytes。"""
    bucket = _get_bucket(**oss_kwargs)
    return bucket.get_object(object_key).read()


def get_sign_url(object_key: str, expires: int = 3600, **oss_kwargs) -> str:
    """生成带签名的临时访问 URL（适用于私有 bucket）。"""
    bucket = _get_bucket(**oss_kwargs)
    return bucket.sign_url("GET", object_key, expires)


def exists(object_key: str, **oss_kwargs) -> bool:
    """检查 object 是否已存在。"""
    bucket = _get_bucket(**oss_kwargs)
    return bucket.object_exists(object_key)
