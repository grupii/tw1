import motor.motor_asyncio
import os
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI environment variable is not set")
        _client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    return _client

def get_db():
    client = get_client()
    db_name = os.getenv("DB_NAME", "xoperation")
    return client[db_name]

def get_accounts_collection():
    collection_name = os.getenv("ACCOUNTS_COLLECTION", "xaccounts")
    return get_db()[collection_name]

def get_group_chats_collection():
    collection_name = os.getenv("GROUP_CHATS_COLLECTION", "xgroup_chats")
    return get_db()[collection_name]

def get_twitter_users_collection():
    return get_db()["xtwitter_users"]

def get_raw_data_collection():
    return get_db()["xraw_data"]
