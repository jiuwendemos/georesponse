"""S3-compatible object storage (MinIO, AWS S3, OSS, OBS)."""

from __future__ import annotations

from pathlib import Path

from .config import PlatformSettings, get_settings


class StorageUnavailable(RuntimeError):
    pass


class S3ObjectStore:
    def __init__(self, settings: PlatformSettings | None = None) -> None:
        self.settings = settings or get_settings().platform
        if not (self.settings.s3_endpoint and self.settings.s3_bucket):
            raise StorageUnavailable("S3 endpoint and bucket are not configured")
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint,
            aws_access_key_id=self.settings.s3_access_key or None,
            aws_secret_access_key=self.settings.s3_secret_key or None,
            region_name="us-east-1",
        )
        self.bucket = self.settings.s3_bucket

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def list(self, prefix: str = "") -> list[dict]:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [
            {"key": item["Key"], "bytes": item["Size"], "modified": item["LastModified"].isoformat()}
            for item in response.get("Contents", [])
        ]

    def presigned(self, key: str, *, expires: int = 900) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)

    def lifecycle(self, prefix: str, *, older_than_days: int) -> int:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        removed = 0
        for item in self.list(prefix):
            if datetime.fromisoformat(item["modified"].replace("Z", "+00:00")) < cutoff:
                self.delete(item["key"])
                removed += 1
        return removed


def health(settings: PlatformSettings | None = None) -> dict:
    settings = settings or get_settings().platform
    configured = bool(settings.s3_endpoint and settings.s3_bucket)
    result = {"configured": configured, "endpoint": settings.s3_endpoint or None, "bucket": settings.s3_bucket or None}
    if not configured:
        return {**result, "ok": False, "detail": "set GEORESPONSE_S3_ENDPOINT and GEORESPONSE_S3_BUCKET"}
    try:
        store = S3ObjectStore(settings)
        store.list("")
        return {**result, "ok": True}
    except Exception as exc:  # noqa: BLE001
        return {**result, "ok": False, "detail": str(exc)}


def build_object_store(settings: PlatformSettings | None = None):  # noqa: ANN201
    from ..proactive.ops import LocalObjectStore

    settings = settings or get_settings().platform
    if settings.s3_endpoint and settings.s3_bucket:
        return S3ObjectStore(settings)
    return LocalObjectStore(Path("runtime/objects"))
