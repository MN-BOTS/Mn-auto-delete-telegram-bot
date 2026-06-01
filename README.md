# 🚀 MN Auto Delete Management Bot

A MongoDB-backed Telegram auto-delete bot built with Pyrogram/pyrotgfork. Every group or channel owner/admin can manage their own delete timer, and pending delete jobs are persisted so they continue after a bot restart.

> **Credits:** Developed by **GitHub.com/mntgxo**<br>
> Source repo: https://github.com/MN-BOTS/Mn-Auto-Delete

---

## ✨ Features

- ✅ **Per-group and per-channel settings** managed by each chat owner/admin.
- ✅ **Default safe mode:** the bot does **not delete anything** until `/setdelete` or `/deleteon` is used in that chat.
- ✅ **Custom delete times up to 1 hour:** supports seconds, minutes, and hours (`10s`, `5m`, `1h`).
- ✅ **MongoDB persistence:** chat settings and pending delete jobs survive restarts.
- ✅ **Restart recovery:** the bot resumes all pending delete schedules from MongoDB on startup.
- ✅ **Proper FloodWait handling** for deleting, admin checks, force-sub checks, and broadcasts.
- ✅ **Multiple force-sub chats** with owner commands to add/remove/list requirements.
- ✅ **Rich dynamic UI** with inline callbacks for start menus, settings, help, owner panels, source links, and force-sub verification.
- ✅ **Owner management panel** with stats for users, chats, enabled chats, force-sub chats, and pending delete jobs.
- ✅ **Forward-method broadcast** to bot PM users, groups, and channels.
- ✅ **Blocked/deleted PM cleanup:** blocked users are automatically removed from MongoDB during broadcast.
- ✅ Hourly group notice system that deletes the previous notice before sending the new one.
- ✅ Automatic Telegram command registration on startup.
- ✅ Flask health check for Koyeb/Render-style deployments.

---

## 🧩 Environment Variables

| Variable | Required | Description | Example |
|---|---:|---|---|
| `TOKEN` | ✅ | Bot token from [@BotFather](https://t.me/BotFather) | `123456:ABCDEF...` |
| `API_ID` | ✅ | Telegram API ID from https://my.telegram.org | `123456` |
| `API_HASH` | ✅ | Telegram API hash | `abcdef123456...` |
| `OWNER` | ✅ | Telegram user ID of the bot owner | `123456789` |
| `MONGO_URI` | ✅ | MongoDB connection URI | `mongodb+srv://user:pass@cluster/db` |
| `DATABASE_NAME` | ❌ | MongoDB database name | `mn_auto_delete` |
| `PORT` | ❌ | Flask health-check port | `8000` |
| `BROADCAST_SLEEP` | ❌ | Small delay between broadcast forwards | `0.05` |
| `NOTICE_INTERVAL` | ❌ | Group notice interval in seconds; defaults to hourly | `3600` |
| `NOTICE_TEXT` | ❌ | Text sent to all known groups every notice interval | `Use /settings to manage me` |

---

## 👥 Group/Channel Admin Commands

Use these inside a group or channel where the bot is present:

| Command | Description |
|---|---|
| `/settings` | Open the dynamic settings panel. |
| `/setdelete 30s` | Enable auto-delete and delete new messages after 30 seconds. |
| `/setdelete 5m` | Enable auto-delete with a 5-minute timer. |
| `/setdelete 1h` | Enable auto-delete with the maximum allowed 1-hour timer. |
| `/setdelete off` | Disable auto-delete. |
| `/deleteon` | Enable auto-delete with saved time, or 60 seconds if no time was saved. |
| `/deleteoff` | Disable auto-delete for new messages. |
| `/help` | Show chat help and repo credits. |

The bot must have permission to delete messages in the group/channel.

---

## 👑 Owner Commands

Use these in the bot PM from the configured `OWNER` account:

| Command | Description |
|---|---|
| `/admin` or `/stats` | Open the owner management panel. |
| `/broadcast` | Reply to any message and broadcast it using Telegram **forward**. |
| `/addfsub <chat_id> [invite_link]` | Add a required force-sub chat. |
| `/delfsub <chat_id>` | Remove a force-sub chat. |
| `/fsubs` | List all configured force-sub chats. |

---

## 🗄️ MongoDB Collections

- `chats` - per-chat settings, status, titles, last hourly notice ID, and metadata.
- `messages` - pending/completed delete jobs with delete timestamps.
- `users` - bot PM users; blocked/deactivated PM users are removed during broadcast.
- `fsubs` - multiple force-sub chat requirements.
- `broadcasts` - broadcast history and delivery stats.

---

## 🚀 Deploy

1. Add the bot to your group/channel as admin with delete permissions.
2. Set the required environment variables.
3. Start the bot:

```bash
python bot.py
```

4. In each chat, run:

```text
/setdelete 30s
```

or open:

```text
/settings
```

---

## ⚠️ Notes

- Default mode is disabled for every chat, so newly added chats are safe.
- Auto-delete timers above 1 hour are rejected.
- Telegram limits are respected through FloodWait sleeps.
- Blocked/deleted PM users are removed from the `users` collection during broadcast.
- This project keeps original credits for **GitHub.com/mntgxo** and the source repository.
