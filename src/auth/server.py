"""FastAPI OAuth2 callback server.

Google redirects here after a user completes the authorization flow.
The `state` query param carries the Discord user ID so we know whose
token to store without needing any server-side session.
"""

import discord
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import exchange_code as _exchange_code

app = FastAPI()

# Set by bot.py in on_ready() so we can DM users after token exchange.
_discord_client: discord.Client | None = None


def set_discord_client(client: discord.Client) -> None:
    global _discord_client
    _discord_client = client


@app.get("/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error or not code or not state:
        return HTMLResponse(
            "<h1>Authorization cancelled</h1>"
            "<p>You can close this tab and try again from Discord.</p>",
            status_code=400,
        )

    try:
        _exchange_code(user_id=state, code=code)
    except Exception as e:
        return HTMLResponse(
            f"<h1>Something went wrong</h1><p>{e}</p>",
            status_code=500,
        )

    # Best-effort DM — don't let a Discord error break the HTTP response.
    if _discord_client:
        try:
            user = await _discord_client.fetch_user(int(state))
            dm = await user.create_dm()
            await dm.send(
                "✅ Google account connected! You can now use all Google Drive features. "
                "Just tell me what you'd like to do."
            )
        except Exception:
            pass

    return HTMLResponse(
        "<h1>Connected!</h1>"
        "<p>Your Google account is linked. You can close this tab and return to Discord.</p>"
    )
