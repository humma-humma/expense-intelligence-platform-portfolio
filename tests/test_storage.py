from io import BytesIO
from typing import cast

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from expense_intelligence.storage import S3ArtifactStorage


class RecordingS3Client:
    def __init__(self, missing_bucket: bool = False) -> None:
        self.missing_bucket = missing_bucket
        self.created: list[str] = []
        self.uploaded: list[dict[str, object]] = []
        self.download = b"stored image"

    def head_bucket(self, **_: object) -> None:
        if self.missing_bucket:
            self.missing_bucket = False
            raise ClientError(
                {
                    "Error": {"Code": "404", "Message": "missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadBucket",
            )

    def create_bucket(self, *, Bucket: str) -> None:
        self.created.append(Bucket)

    def put_object(self, **kwargs: object) -> None:
        self.uploaded.append(kwargs)

    def get_object(self, **_: object) -> dict[str, object]:
        return {"Body": BytesIO(self.download)}


def storage_with(client: RecordingS3Client) -> S3ArtifactStorage:
    storage = object.__new__(S3ArtifactStorage)
    storage.bucket = "receipts"
    storage.region = "eu-central-1"
    storage.server_side_encryption = False
    storage.client = cast(BaseClient, client)
    return storage


def test_storage_creates_missing_bucket_and_uploads() -> None:
    client = RecordingS3Client(missing_bucket=True)
    storage = storage_with(client)

    storage.ensure_bucket()
    storage.put("receipt.png", b"image", "image/png")
    storage.check()

    assert client.created == ["receipts"]
    assert client.uploaded[0]["Key"] == "receipt.png"
    assert storage.get("receipt.png") == b"stored image"
