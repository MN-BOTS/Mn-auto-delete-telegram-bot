import asyncio
import heapq
import logging
import threading
import time
from itertools import count

from flask import Flask
from werkzeug.serving import make_server
from pyrogram import Client
from pyrogram import utils as pyroutils
from pyrogram.types import BotCommand

from config import BOT, API, OWNER, WEB, NOTICE
import database
from utils import safe_delete, safe_delete_plain, send_with_flood

# Preserve compatibility with large Telegram group/channel IDs.
pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -10099999999999

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)


@app.route("/")
def home():
    return "MN Auto Delete Bot is running! Credits: GitHub.com/mntgxo"


def run_flask():
    server = make_server("0.0.0.0", WEB.PORT, app)
    logging.info("Health check server running on port %s", WEB.PORT)
    server.serve_forever()


class MN_Bot(Client):
    """Kurigram client with a single priority-queue scheduler and bounded workers."""

    def __init__(self):
        super().__init__(
            "MN-Bot",
            api_id=API.ID,
            api_hash=API.HASH,
            bot_token=BOT.TOKEN,
            plugins=dict(root="plugins"),
            workers=32,
        )
        self._delete_heap = []
        self._delete_tokens = {}
        self._sequence = count()
        self._scheduler_wakeup = asyncio.Event()
        self._delete_queue = asyncio.Queue(maxsize=1000)
        self._scheduler_task = None
        self._delete_workers = []
        self._notice_task = None
        self._stopping = False

    async def start(self):
        database.init_db()
        await super().start()
        me = await self.get_me()
        BOT.USERNAME = f"@{me.username}"
        self.mention = me.mention
        self.username = me.username
        await self.register_commands()

        # Start one dispatcher and a bounded number of workers rather than one
        # sleeping asyncio task per scheduled message.
        self._stopping = False
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._delete_workers = [
            asyncio.create_task(self._delete_worker()) for _ in range(8)
        ]
        await self.resume_pending_deletes()
        self._notice_task = asyncio.create_task(self.hourly_group_notices())

        startup_text = (
            f"{me.first_name} ✅ BOT started successfully\n"
            "Persistent auto-delete scheduler resumed from MongoDB.\n"
            "Commands registered automatically.\n"
            "Credits: GitHub.com/mntgxo"
        )
        if OWNER.ID:
            await send_with_flood(self, OWNER.ID, startup_text)
        logging.info("✅ %s BOT started successfully", me.first_name)

    async def stop(self, *args):
        self._stopping = True
        self._scheduler_wakeup.set()
        tasks = [task for task in [self._scheduler_task, self._notice_task] if task]
        tasks.extend(self._delete_workers)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await super().stop()
        logging.info("Bot stopped")

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
        try:
            await self.set_bot_commands(commands)
        except Exception as err:
            logging.warning("Failed to register bot commands: %s", err)

    def schedule_delete(self, chat_id, message_id, delete_at):
        """Schedule/reschedule a message without allocating a sleeping task."""
        key = (int(chat_id), int(message_id))
        delete_at = database.normalize_dt(delete_at)
        if delete_at is None:
            return
        deadline = delete_at.timestamp()
        token = next(self._sequence)
        self._delete_tokens[key] = token
        heapq.heappush(self._delete_heap, (deadline, token, key))
        self._scheduler_wakeup.set()

    async def _scheduler_loop(self):
        while not self._stopping:
            # Drop stale heap entries left by a reschedule.
            while self._delete_heap:
                deadline, token, key = self._delete_heap[0]
                if self._delete_tokens.get(key) == token:
                    break
                heapq.heappop(self._delete_heap)

            if not self._delete_heap:
                self._scheduler_wakeup.clear()
                await self._scheduler_wakeup.wait()
                continue

            deadline, token, key = self._delete_heap[0]
            remaining = deadline - time.time()
            if remaining > 0:
                self._scheduler_wakeup.clear()
                try:
                    await asyncio.wait_for(self._scheduler_wakeup.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
                continue

            heapq.heappop(self._delete_heap)
            if self._delete_tokens.get(key) != token:
                continue
            self._delete_tokens.pop(key, None)
            await self._delete_queue.put((key[0], key[1]))

    async def _delete_worker(self):
        while True:
            chat_id, message_id = await self._delete_queue.get()
            try:
                await safe_delete(self, chat_id, message_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Delete worker failed for %s/%s", chat_id, message_id)
            finally:
                self._delete_queue.task_done()

    async def resume_pending_deletes(self):
        # Existing public database helper returns at most 5000 records.
        # Keep its established behavior and avoid changing persisted schemas.
        items = await asyncio.to_thread(database.pending_messages, 5000)
        for item in items:
            self.schedule_delete(item["chat_id"], item["message_id"], item["delete_at"])
        logging.info("Resumed %s pending delete jobs from MongoDB", len(items))

    async def hourly_group_notices(self):
        while True:
            try:
                await self.send_group_notices()
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Hourly notice loop failed")
            await asyncio.sleep(max(60, NOTICE.INTERVAL))

    async def send_group_notices(self):
        chats = await asyncio.to_thread(database.notice_chats)
        sent = 0
        for chat in chats:
            chat_id = chat["_id"]
            await safe_delete_plain(self, chat_id, chat.get("last_notice_message_id"))
            message = await send_with_flood(
                self, chat_id, NOTICE.TEXT, disable_web_page_preview=True
            )
            if message:
                await asyncio.to_thread(database.save_notice_message, chat_id, message.id)
                sent += 1
            else:
                await asyncio.to_thread(database.clear_notice_message, chat_id, "send_failed")
        logging.info("Hourly notice sent to %s groups", sent)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    MN_Bot().run()
