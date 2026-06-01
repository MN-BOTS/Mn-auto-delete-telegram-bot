import asyncio
from pyrogram.errors import (
    FloodWait,
    UserIsBlocked,
    InputUserDeactivated,
    PeerIdInvalid,
    ChatWriteForbidden,
    ChannelPrivate,
    ChatAdminRequired,
    MessageDeleteForbidden,
    MessageIdInvalid,
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import database

OWNER_STATUSES = {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}
BLOCK_ERRORS = (UserIsBlocked, InputUserDeactivated, PeerIdInvalid)
CHAT_ERRORS = (ChatWriteForbidden, ChannelPrivate, ChatAdminRequired)
DELETE_IGNORED_ERRORS = (MessageDeleteForbidden, MessageIdInvalid)
MAX_DELETE_SECONDS = 3600
REPO_URL = "https://github.com/MN-BOTS/Mn-Auto-Delete"
DEV_URL = "https://github.com/mntgxo"


def human_time(seconds):
    seconds = int(seconds)
    if seconds <= 0:
        return "Off"
    units = ((3600, "h"), (60, "m"), (1, "s"))
    parts = []
    for size, suffix in units:
        value, seconds = divmod(seconds, size)
        if value:
            parts.append(f"{value}{suffix}")
    return " ".join(parts) or "0s"


def parse_time(value):
    if not value:
        raise ValueError("missing time")
    raw = value.strip().lower()
    if raw in {"off", "disable", "disabled", "0"}:
        return 0
    suffix = raw[-1]
    number = raw[:-1] if suffix.isalpha() else raw
    if not number.isdigit():
        raise ValueError("invalid time")
    amount = int(number)
    multipliers = {"s": 1, "m": 60, "h": 3600}
    if suffix.isalpha() and suffix not in multipliers:
        raise ValueError("supported units are s, m, and h")
    seconds = amount * multipliers.get(suffix, 1)
    if seconds < 0 or seconds > MAX_DELETE_SECONDS:
        raise ValueError("auto-delete time cannot be more than 1 hour")
    return seconds


async def sleep_flood(seconds):
    await asyncio.sleep(int(seconds) + 1)


async def safe_delete(client, chat_id, message_id):
    while True:
        try:
            await client.delete_messages(chat_id, message_id)
            database.finish_scheduled_message(chat_id, message_id, "deleted")
            return True
        except FloodWait as fw:
            await sleep_flood(fw.value)
        except DELETE_IGNORED_ERRORS as err:
            database.finish_scheduled_message(chat_id, message_id, "skipped", str(err))
            return False
        except Exception as err:
            database.finish_scheduled_message(chat_id, message_id, "failed", str(err))
            return False


async def safe_delete_plain(client, chat_id, message_id):
    if not message_id:
        return False
    while True:
        try:
            await client.delete_messages(chat_id, message_id)
            return True
        except FloodWait as fw:
            await sleep_flood(fw.value)
        except Exception:
            return False


async def forward_with_flood(message, chat_id):
    while True:
        try:
            await message.forward(chat_id)
            return "sent"
        except FloodWait as fw:
            await sleep_flood(fw.value)
        except BLOCK_ERRORS:
            database.remove_user(chat_id)
            return "blocked_removed"
        except CHAT_ERRORS:
            return "forbidden"
        except Exception:
            return "failed"


async def send_with_flood(client, chat_id, text, **kwargs):
    while True:
        try:
            return await client.send_message(chat_id, text, **kwargs)
        except FloodWait as fw:
            await sleep_flood(fw.value)
        except Exception:
            return None


async def is_chat_admin(client, chat_id, user_id):
    if not user_id:
        return False
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in OWNER_STATUSES
    except FloodWait as fw:
        await sleep_flood(fw.value)
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in OWNER_STATUSES
    except Exception:
        return False


def settings_keyboard(chat_id, enabled):
    toggle = "Disable 📴" if enabled else "Enable ✅"
    action = "off" if enabled else "on"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(toggle, callback_data=f"set:{chat_id}:{action}")],
            [
                InlineKeyboardButton("15s", callback_data=f"delay:{chat_id}:15"),
                InlineKeyboardButton("30s", callback_data=f"delay:{chat_id}:30"),
                InlineKeyboardButton("1m", callback_data=f"delay:{chat_id}:60"),
            ],
            [
                InlineKeyboardButton("5m", callback_data=f"delay:{chat_id}:300"),
                InlineKeyboardButton("30m", callback_data=f"delay:{chat_id}:1800"),
                InlineKeyboardButton("1h Max", callback_data=f"delay:{chat_id}:3600"),
            ],
            [InlineKeyboardButton("Help 📘", callback_data=f"chathelp:{chat_id}"), InlineKeyboardButton("Refresh 🔄", callback_data=f"settings:{chat_id}")],
        ]
    )


def start_keyboard(fsubs=None):
    rows = []
    for sub in fsubs or []:
        label = sub.get("title") or sub.get("username") or str(sub["_id"])
        link = sub.get("invite_link") or (f"https://t.me/{sub['username']}" if sub.get("username") else None)
        if link:
            rows.append([InlineKeyboardButton(f"Join {label}", url=link)])
    rows.append([InlineKeyboardButton("✅ I Joined", callback_data="check_fsub")])
    rows.append([InlineKeyboardButton("Repo ⭐", url=REPO_URL)])
    return InlineKeyboardMarkup(rows)


def main_menu_keyboard(is_owner=False):
    rows = [
        [InlineKeyboardButton("Commands 📚", callback_data="start:commands"), InlineKeyboardButton("Features ✨", callback_data="start:features")],
        [InlineKeyboardButton("Credits 👨‍💻", callback_data="start:credits"), InlineKeyboardButton("Help 🛠", callback_data="start:help")],
        [InlineKeyboardButton("Repo ⭐", url=REPO_URL), InlineKeyboardButton("Developer", url=DEV_URL)],
    ]
    if is_owner:
        rows.insert(0, [InlineKeyboardButton("Owner Panel 👑", callback_data="owner:panel")])
    return InlineKeyboardMarkup(rows)


def back_home_keyboard(is_owner=False):
    rows = [[InlineKeyboardButton("🏠 Home", callback_data="start:home")]]
    if is_owner:
        rows.append([InlineKeyboardButton("Owner Panel 👑", callback_data="owner:panel")])
    rows.append([InlineKeyboardButton("Repo ⭐", url=REPO_URL)])
    return InlineKeyboardMarkup(rows)


def home_text():
    return (
        "**👋 Welcome to MN Auto Delete Bot**\n\n"
        "Manage auto-delete timers with MongoDB persistence, rich buttons, force-sub, broadcasts, and restart-safe schedules.\n\n"
        "Default mode is safe: no chat deletes anything until its admin enables auto-delete."
    )


def commands_text():
    return (
        "**📚 Commands**\n\n"
        "**Group/Channel Admin**\n"
        "• `/settings` - open settings UI\n"
        "• `/setdelete 30s` - set delete time\n"
        "• `/setdelete off` - disable auto-delete\n"
        "• `/deleteon` / `/deleteoff` - quick toggle\n\n"
        "**Owner PM**\n"
        "• `/admin` - owner panel\n"
        "• `/broadcast` - reply and forward everywhere\n"
        "• `/addfsub`, `/delfsub`, `/fsubs` - force-sub manager"
    )


def features_text():
    return (
        "**✨ Features**\n\n"
        "• Per-group/channel custom timers\n"
        "• Max delete time: 1 hour\n"
        "• MongoDB restart recovery\n"
        "• Proper FloodWait handling\n"
        "• Multiple force-sub chats\n"
        "• Forward-method broadcasts\n"
        "• Blocked PM users removed from DB\n"
        "• Hourly group notice replaces the previous notice"
    )


def credits_text():
    return f"**👨‍💻 Credits**\n\nDeveloper: GitHub.com/mntgxo\nRepo: {REPO_URL}"


def settings_text(chat, settings):
    state = "Enabled ✅" if settings.get("enabled") else "Disabled 📴"
    delay = human_time(settings.get("delete_delay", 0))
    return (
        f"**🛠 Auto Delete Settings**\n\n"
        f"**Chat:** {chat.title or chat.id}\n"
        f"**ID:** `{chat.id}`\n"
        f"**Status:** {state}\n"
        f"**Delete Time:** `{delay}`\n"
        f"**Limit:** `1 hour max`\n\n"
        "Use buttons below or `/setdelete 30s`, `/setdelete 5m`, `/setdelete 1h`, `/setdelete off`."
    )


def chat_help_text():
    return (
        "**📘 Auto Delete Help**\n\n"
        "Only group/channel owners and admins can change settings.\n"
        "Allowed units: seconds (`s`), minutes (`m`), hours (`h`).\n"
        "Maximum allowed auto-delete time is **1 hour**.\n\n"
        "Examples: `/setdelete 15s`, `/setdelete 5m`, `/setdelete 1h`, `/setdelete off`."
    )
