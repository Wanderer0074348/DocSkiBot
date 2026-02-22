"""Application entry point.

This file starts two long-running coroutines concurrently inside a single
asyncio event loop:

  1. uvicorn (FastAPI) — serves the OAuth2 callback at /oauth/callback so
     Google can redirect back after a user authorises the app. See src/auth/.

  2. discord.Client — the bot that receives DMs, invokes the LangGraph agent,
     and renders Discord UI (buttons, modals, select menus). See src/skills/bot.py.

Running both in one event loop (via asyncio.gather) means they share the same
thread pool and avoid the overhead of inter-process communication. If you ever
need to scale or isolate them, split into two processes and communicate via a
message queue or shared database instead of module-level globals.

Environment variables required (see .env.example):
  DISCORD_BOT_TOKEN     — from Discord Developer Portal
  OAUTH_CALLBACK_PORT   — port uvicorn listens on (default 8080)
  ANTHROPIC_API_KEY     — passed through to LangChain in agent.py
"""

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from src.logger import setup_logging
setup_logging()

import logging
import uvicorn

logger = logging.getLogger(__name__)
from src.auth.server import app      # FastAPI app — /oauth/callback route
from src.skills.bot import client    # discord.Client instance


async def main():
    port = int(os.getenv("OAUTH_CALLBACK_PORT", "8080"))
    logger.info("Starting — uvicorn on :%d + Discord bot", port)

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    token = os.environ["DISCORD_BOT_TOKEN"]

    await asyncio.gather(
        server.serve(),
        client.start(token),
    )


if __name__ == "__main__":
    asyncio.run(main())
