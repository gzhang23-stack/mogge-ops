from __future__ import annotations

import os
from dataclasses import dataclass

import boto3


@dataclass
class StorageConfig:
    endpoint_url: str | None = os.getenv("S3_ENDPOINT_URL")
    access_key: str | None = os.getenv("S3_ACCESS_KEY")
    secret_key: str | None = os.getenv("S3_SECRET_KEY")
    bucket: str = os.getenv("S3_BUCKET", "mogge-assets")


class AssetStorage:
    def __init__(self, config: StorageConfig | None = None):
        self.config = config or StorageConfig()

    def enabled(self) -> bool:
        return bool(self.config.endpoint_url and self.config.access_key and self.config.secret_key)

    def put_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        if not self.enabled():
            local_dir = os.path.abspath("asset_uploads")
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, key.replace("/", "_"))
            with open(local_path, "wb") as file:
                file.write(content)
            return local_path
        client = boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
        )
        client.put_object(Bucket=self.config.bucket, Key=key, Body=content, ContentType=content_type)
        return f"{self.config.endpoint_url.rstrip('/')}/{self.config.bucket}/{key}"

