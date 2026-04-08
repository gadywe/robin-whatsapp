import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Green API
GREEN_API_URL = os.getenv("GREEN_API_URL")
GREEN_API_INSTANCE = os.getenv("GREEN_API_INSTANCE")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL = "claude-sonnet-4-5"

# Agent
AGENT_NAME = "רובין"
MAX_HISTORY = 20
