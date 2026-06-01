from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from config import DATABASE

_client = MongoClient(DATABASE.URI)
db = _client[DATABASE.NAME]

chats = db.chats
messages = db.messages
users = db.users
fsubs = db.fsubs
broadcasts = db.broadcasts


def init_db():
    chats.create_index([("enabled", ASCENDING)])
    chats.create_index([("type", ASCENDING)])
    messages.create_index([("delete_at", ASCENDING)])
    messages.create_index([("chat_id", ASCENDING), ("message_id", ASCENDING)], unique=True)
    users.create_index([("blocked", ASCENDING)])
    if "chat_id_1" in fsubs.index_information():
        fsubs.drop_index("chat_id_1")
    fsubs.create_index([("title", ASCENDING)])


def now_utc():
    return datetime.now(timezone.utc)


def normalize_dt(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def upsert_user(user):
    if not user:
        return
    users.update_one(
        {"_id": user.id},
        {
            "$set": {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username,
                "blocked": False,
                "last_seen": now_utc(),
            },
            "$setOnInsert": {"created_at": now_utc()},
        },
        upsert=True,
    )


def mark_blocked(user_id):
    users.update_one(
        {"_id": int(user_id)},
        {"$set": {"blocked": True, "blocked_at": now_utc()}},
        upsert=True,
    )


def remove_user(user_id):
    users.delete_one({"_id": int(user_id)})


def save_chat(chat, user_id=None):
    if not chat:
        return
    chats.update_one(
        {"_id": chat.id},
        {
            "$set": {
                "title": getattr(chat, "title", None) or getattr(chat, "first_name", None),
                "type": str(chat.type),
                "username": getattr(chat, "username", None),
                "updated_at": now_utc(),
                "updated_by": user_id,
            },
            "$setOnInsert": {
                "enabled": False,
                "delete_delay": 0,
                "created_at": now_utc(),
            },
        },
        upsert=True,
    )


def get_chat_settings(chat_id):
    return chats.find_one({"_id": int(chat_id)}) or {"_id": int(chat_id), "enabled": False, "delete_delay": 0}


def set_chat_settings(chat, user_id, *, enabled=None, delete_delay=None):
    save_chat(chat, user_id)
    payload = {"updated_at": now_utc(), "updated_by": user_id}
    if enabled is not None:
        payload["enabled"] = bool(enabled)
    if delete_delay is not None:
        payload["delete_delay"] = int(delete_delay)
    chats.update_one({"_id": chat.id}, {"$set": payload}, upsert=True)
    return get_chat_settings(chat.id)


def save_scheduled_message(chat_id, message_id, delete_at):
    messages.update_one(
        {"chat_id": int(chat_id), "message_id": int(message_id)},
        {
            "$set": {
                "chat_id": int(chat_id),
                "message_id": int(message_id),
                "delete_at": delete_at,
                "status": "pending",
                "updated_at": now_utc(),
            },
            "$setOnInsert": {"created_at": now_utc()},
        },
        upsert=True,
    )


def finish_scheduled_message(chat_id, message_id, status="deleted", error=None):
    messages.update_one(
        {"chat_id": int(chat_id), "message_id": int(message_id)},
        {"$set": {"status": status, "error": error, "updated_at": now_utc()}},
    )


def pending_messages(limit=500):
    return list(messages.find({"status": "pending"}).sort("delete_at", ASCENDING).limit(limit))


def add_fsub(chat_id, title=None, username=None, invite_link=None):
    fsubs.update_one(
        {"_id": int(chat_id)},
        {
            "$set": {
                "title": title,
                "username": username,
                "invite_link": invite_link,
                "updated_at": now_utc(),
            },
            "$setOnInsert": {"created_at": now_utc()},
        },
        upsert=True,
    )


def remove_fsub(chat_id):
    fsubs.delete_one({"_id": int(chat_id)})


def list_fsubs():
    return list(fsubs.find().sort("title", ASCENDING))


def notice_chats():
    return list(chats.find({"type": {"$regex": "GROUP"}}).sort("title", ASCENDING))


def save_notice_message(chat_id, message_id):
    chats.update_one(
        {"_id": int(chat_id)},
        {"$set": {"last_notice_message_id": int(message_id), "last_notice_at": now_utc()}},
    )


def clear_notice_message(chat_id, error=None):
    payload = {"last_notice_message_id": None, "last_notice_error": error, "last_notice_at": now_utc()}
    chats.update_one({"_id": int(chat_id)}, {"$set": payload})
