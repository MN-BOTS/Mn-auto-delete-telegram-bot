from dotenv import load_dotenv
load_dotenv()

import os

class BOT:
    TOKEN = os.environ.get("TOKEN", "")
    USERNAME = ""

class API:
    HASH = os.environ.get("API_HASH", "")
    ID = int(os.environ.get("API_ID", 0))

class OWNER:
    ID = int(os.environ.get("OWNER", 0))

class WEB:
    PORT = int(os.environ.get("PORT", 8000))

class DATABASE:
    URI = os.environ.get("MONGO_URI", os.environ.get("DATABASE_URI", "mongodb://localhost:27017"))
    NAME = os.environ.get("DATABASE_NAME", "mn_auto_delete")

class BROADCAST:
    SLEEP = float(os.environ.get("BROADCAST_SLEEP", "0.05"))

class NOTICE:
    INTERVAL = int(os.environ.get("NOTICE_INTERVAL", "3600"))
    TEXT = os.environ.get(
        "NOTICE_TEXT",
        "🧹 MN Auto Delete is active. Use /settings to manage auto-delete. Credits: GitHub.com/mntgxo",
    )
