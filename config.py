import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_TELEGRAM_ID: int = int(os.environ["ADMIN_TELEGRAM_ID"])
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "avito_bot.db")
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "20"))  # seconds
