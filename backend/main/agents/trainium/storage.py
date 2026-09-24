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


async def open_range(file_id: str, start: int, length: int):
    """Yield a byte range of a stored file, in chunks.

    Video needs this: a browser seeking to the middle of a recording sends a
    Range request, and answering it by loading the whole file would buffer a
    hundred megabytes per seek. GridFS can seek natively, so only the slice
    asked for is read.
    """
    from bson import ObjectId

    stream = await _bucket.open_download_stream(ObjectId(file_id))
    try:
        stream.seek(start)
        remaining = length
        while remaining > 0:
            chunk = await stream.readchunk()
            if not chunk:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            remaining -= len(chunk)
            yield chunk
    finally:
        stream.close()


async def file_size(file_id: str) -> int:
    """Byte length of a stored file, without reading it."""
    from bson import ObjectId

    stream = await _bucket.open_download_stream(ObjectId(file_id))
    try:
        return stream.length
    finally:
        stream.close()


async def delete_file(file_id: str) -> None:
    from bson import ObjectId

    await _bucket.delete(ObjectId(file_id))
