import abc
import logging
from pathlib import Path
import aiofiles
from botocore.config import Config
from botocore.exceptions import ClientError
import aioboto3

from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseStorage(abc.ABC):
    @abc.abstractmethod
    async def put(self, key: str, data: bytes) -> str:
        """Stores file bytes and returns the reference key."""
        pass

    @abc.abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieves raw bytes using the reference key."""
        pass

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Removes the file from storage."""
        pass


class LocalStorage(BaseStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        return self.base_dir / Path(key).name

    async def put(self, key: str, data: bytes) -> str:
        target_path = self._resolve_path(key)
        async with aiofiles.open(target_path, "wb") as f:
            await f.write(data)
        return str(target_path)

    async def get(self, key: str) -> bytes:
        target_path = self._resolve_path(key)
        if not target_path.exists():
            raise FileNotFoundError(f"Local file not found: {target_path}")
        async with aiofiles.open(target_path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        target_path = self._resolve_path(key)
        target_path.unlink(missing_ok=True)


class R2Storage(BaseStorage):
    def __init__(self):
        self.session = aioboto3.Session()
        self.config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        )

    def _client(self):
        return self.session.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=self.config,
        )

    async def put(self, key: str, data: bytes) -> str:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=key,
                Body=data,
            )
            return key

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            try:
                response = await s3.get_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=key,
                )
                async with response["Body"] as stream:
                    return await stream.read()
            except ClientError as e:
                raise FileNotFoundError(f"R2 key not found: {key}") from e

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            try:
                await s3.delete_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=key,
                )
            except ClientError:
                pass


# Strategy Selector
def get_storage() -> BaseStorage:
    if settings.STORAGE_BACKEND == "r2":
        return R2Storage()
    return LocalStorage(settings.UPLOAD_LOCAL_DIR)


storage = get_storage()