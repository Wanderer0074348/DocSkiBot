import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from src.auth.server import app
from src.skills.bot import client


async def main():
    port = int(os.getenv("OAUTH_CALLBACK_PORT", "8080"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    token = os.environ["DISCORD_BOT_TOKEN"]
    await asyncio.gather(
        server.serve(),
        client.start(token),
    )


if __name__ == "__main__":
    asyncio.run(main())
