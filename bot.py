import asyncio
import logging
import threading
from flask import Flask
from pyrogram import Client
from pyrogram import utils as pyroutils
from pyrogram.types import BotCommand
from config import BOT, API, OWNER, WEB, NOTICE
import database
from utils import safe_delete, safe_delete_plain, send_with_flood

# ✅ Peer ID Fix (for large channel/group IDs)
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -10099999999999

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

app = Flask(__name__)

@app.route('/')
def home():
    return "MN Auto Delete Bot is running! Credits: GitHub.com/mntgxo"

def run_flask():
    app.run(host='0.0.0.0', port=WEB.PORT)

class MN_Bot(Client):
    def __init__(self):
        super().__init__(
            "MN-Bot",
            api_id=API.ID,
            api_hash=API.HASH,
            bot_token=BOT.TOKEN,
            plugins=dict(root="plugins"),
            workers=32,
        )
        self.delete_tasks = {}
        self.notice_task = None

    async def start(self):
        database.init_db()
        await super().start()
        me = await self.get_me()
        BOT.USERNAME = f"@{me.username}"
        self.mention = me.mention
        self.username = me.username
        await self.register_commands()
        await self.resume_pending_deletes()
        self.notice_task = asyncio.create_task(self.hourly_group_notices())
        text = (
            f"{me.first_name} ✅ BOT started successfully\n"
            "Persistent auto-delete scheduler resumed from MongoDB.\n"
            "Commands registered automatically.\n"
            "Credits: GitHub.com/mntgxo"
        )
        if OWNER.ID:
            await self.send_message(chat_id=OWNER.ID, text=text)
        logging.info("✅ %s BOT started successfully", me.first_name)

    async def stop(self, *args):
        for task in self.delete_tasks.values():
            task.cancel()
        if self.notice_task:
            self.notice_task.cancel()
        await super().stop()
        logging.info("Bot Stopped 🙄")

    async def register_commands(self):
        commands = [
            BotCommand("start", "Open the rich bot menu"),
            BotCommand("settings", "Open group/channel auto-delete settings"),
            BotCommand("setdelete", "Set auto-delete time up to 1 hour"),
            BotCommand("deleteon", "Enable auto-delete in this chat"),
            BotCommand("deleteoff", "Disable auto-delete in this chat"),
            BotCommand("help", "Show help and credits"),
            BotCommand("admin", "Owner management panel"),
            BotCommand("broadcast", "Owner: forward a replied message everywhere"),
            BotCommand("addfsub", "Owner: add force-sub chat"),
            BotCommand("delfsub", "Owner: remove force-sub chat"),
            BotCommand("fsubs", "Owner: list force-sub chats"),
            BotCommand("stats", "Owner: show bot stats"),
        ]
        await self.set_bot_commands(commands)

    def schedule_delete(self, chat_id, message_id, delete_at):
        key = f"{chat_id}:{message_id}"
        old_task = self.delete_tasks.pop(key, None)
        if old_task:
            old_task.cancel()
        self.delete_tasks[key] = asyncio.create_task(self._delete_later(key, chat_id, message_id, delete_at))

    async def _delete_later(self, key, chat_id, message_id, delete_at):
        try:
            delete_at = database.normalize_dt(delete_at)
            delay = max(0, (delete_at - database.now_utc()).total_seconds())
            if delay:
                await asyncio.sleep(delay)
            await safe_delete(self, chat_id, message_id)
        finally:
            self.delete_tasks.pop(key, None)

    async def resume_pending_deletes(self):
        count = 0
        for item in database.pending_messages(limit=5000):
            self.schedule_delete(item["chat_id"], item["message_id"], item["delete_at"])
            count += 1
        logging.info("Resumed %s pending delete jobs from MongoDB", count)

    async def hourly_group_notices(self):
        while True:
            await self.send_group_notices()
            await asyncio.sleep(max(60, NOTICE.INTERVAL))

    async def send_group_notices(self):
        sent = 0
        for chat in database.notice_chats():
            chat_id = chat["_id"]
            await safe_delete_plain(self, chat_id, chat.get("last_notice_message_id"))
            message = await send_with_flood(
                self,
                chat_id,
                NOTICE.TEXT,
                disable_web_page_preview=True,
            )
            if message:
                database.save_notice_message(chat_id, message.id)
                sent += 1
            else:
                database.clear_notice_message(chat_id, "send_failed")
        logging.info("Hourly notice sent to %s groups", sent)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    MN_Bot().run()
