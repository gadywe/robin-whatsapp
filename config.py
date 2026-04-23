import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Green API (kept for reference)
GREEN_API_URL = os.getenv("GREEN_API_URL")
GREEN_API_INSTANCE = os.getenv("GREEN_API_INSTANCE")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")

# Meta WhatsApp Cloud API
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "robin_webhook_2026")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL = "claude-haiku-4-5-20251001"

# OpenAI Whisper (transcription)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Google Calendar
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# PostgreSQL (Neon)
DATABASE_URL = os.getenv("DATABASE_URL")

# Cron (for reminders)
CRON_SECRET = os.getenv("CRON_SECRET", "robin_cron_secret_2026")

# Taskboard (Supabase)
TASKBOARD_SUPABASE_URL = os.getenv("TASKBOARD_SUPABASE_URL", "https://zycgmonggluwhvvkrwmf.supabase.co")
TASKBOARD_SUPABASE_KEY = os.getenv("TASKBOARD_SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp5Y2dtb25nZ2x1d2h2dmtyd21mIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxNjE2MDcsImV4cCI6MjA5MTczNzYwN30.F906h08Ss-VtH6F8d1rIROeOFuk120wyOHT5x6s2rI8")

# Gadi's WhatsApp number
GADI_PHONE = os.getenv("GADI_PHONE", "972552909434")

# Agent
AGENT_NAME = "רובין"
MAX_HISTORY = 10
