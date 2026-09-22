from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from main.db import db

# GridFS stands in for S3 until a real bucket exists (see project memory:
# trainium-gridfs-not-s3). Every caller goes through this module so the
# storage backend can be swapped later without touching route code.
_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="trainium_assets")


async def upload_file(filename: str, content: bytes, content_type: str) -> str:
    file_id = await _bucket.upload_from_stream(
        filename, content, metadata={"content_type": content_type}
    )
    return str(file_id)


async def download_file(file_id: str) -> bytes:
    from bson import ObjectId

    stream = await _bucket.open_download_stream(ObjectId(file_id))
    return await stream.read()


async def delete_file(file_id: str) -> None:
    from bson import ObjectId

    await _bucket.delete(ObjectId(file_id))
