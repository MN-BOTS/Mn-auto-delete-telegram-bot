from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserNotParticipant
from config import OWNER
import database
from utils import (
    start_keyboard,
    sleep_flood,
    main_menu_keyboard,
    back_home_keyboard,
    home_text,
    commands_text,
    features_text,
    credits_text,
    chat_help_text,
)

async def missing_fsubs(client, user_id):
    missing = []
    for sub in database.list_fsubs():
        try:
            await client.get_chat_member(sub["_id"], user_id)
        except FloodWait as fw:
            await sleep_flood(fw.value)
            try:
                await client.get_chat_member(sub["_id"], user_id)
            except UserNotParticipant:
                missing.append(sub)
            except Exception:
                missing.append(sub)
        except UserNotParticipant:
            missing.append(sub)
        except Exception:
            missing.append(sub)
    return missing

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    database.upsert_user(message.from_user)
    missing = await missing_fsubs(client, message.from_user.id)
    if missing:
        await message.reply_text(
            "**🔐 Force Subscribe Required**\n\n"
            "Please join every required channel/group, then tap **I Joined**.",
            reply_markup=start_keyboard(missing),
            disable_web_page_preview=True,
        )
        return

    await message.reply_text(
        home_text(),
        reply_markup=main_menu_keyboard(message.from_user.id == OWNER.ID),
        disable_web_page_preview=True,
    )

@Client.on_callback_query(filters.regex("^check_fsub$"))
async def check_fsub(client, query):
    database.upsert_user(query.from_user)
    missing = await missing_fsubs(client, query.from_user.id)
    if missing:
        await query.answer("Please join all required chats first.", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=start_keyboard(missing))
        return
    await query.answer("Verified ✅", show_alert=True)
    await query.message.edit_text(
        home_text(),
        reply_markup=main_menu_keyboard(query.from_user.id == OWNER.ID),
        disable_web_page_preview=True,
    )

@Client.on_callback_query(filters.regex(r"^start:"))
async def start_callbacks(client, query):
    database.upsert_user(query.from_user)
    missing = await missing_fsubs(client, query.from_user.id)
    if missing:
        await query.answer("Join all required chats first.", show_alert=True)
        await query.message.edit_text(
            "**🔐 Force Subscribe Required**\n\nPlease join every required channel/group, then tap **I Joined**.",
            reply_markup=start_keyboard(missing),
            disable_web_page_preview=True,
        )
        return

    action = query.data.split(":", 1)[1]
    is_owner = query.from_user.id == OWNER.ID
    if action == "home":
        text = home_text()
        keyboard = main_menu_keyboard(is_owner)
    elif action == "commands":
        text = commands_text()
        keyboard = back_home_keyboard(is_owner)
    elif action == "features":
        text = features_text()
        keyboard = back_home_keyboard(is_owner)
    elif action == "credits":
        text = credits_text()
        keyboard = back_home_keyboard(is_owner)
    else:
        text = chat_help_text()
        keyboard = back_home_keyboard(is_owner)

    await query.answer("Updated ✨")
    await query.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
