from motor.motor_asyncio import AsyncIOMotorClient

from main.config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.mongo_db_name]
