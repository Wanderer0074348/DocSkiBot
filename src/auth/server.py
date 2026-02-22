"""FastAPI OAuth2 callback server.

This module is the receiving end of the Google OAuth2 flow. It exposes a single
HTTP GET endpoint that Google redirects the user to after they approve (or deny)
the app on the consent screen.

HOW IT FITS IN THE FLOW
------------------------
  1. bot.py sends the user a "Connect Google" button with a URL built by
     auth.get_auth_url(user_id).
  2. User clicks → browser opens Google consent screen.
  3. User approves → Google redirects to:
       <OAUTH_REDIRECT_URI>/oauth/callback?code=<one_time_code>&state=<discord_user_id>
  4. THIS FILE handles that redirect:
       a. Exchanges the code for credentials (auth.exchange_code).
       b. DMs the user on Discord to confirm success.
       c. Returns an HTML page the user sees in their browser.

THE `state` PARAMETER
----------------------
We embed the Discord user_id in the OAuth `state` parameter when building the
auth URL. Google echoes it back unchanged on the callback. This lets us map the
incoming token back to the right Discord user without any server-side session,
cookies, or database lookups. It's a standard stateless OAuth2 pattern.

SECURITY NOTE
-------------
For production use, the OAUTH_REDIRECT_URI should be HTTPS. If running locally
or in Docker without a reverse proxy, use Cloudflare Tunnel or ngrok so Google
can reach your callback over a secure connection:
  cloudflared tunnel --url http://localhost:8080
The generated URL (e.g. https://random.trycloudflare.com) becomes OAUTH_REDIRECT_URI.

WIRING THE DISCORD CLIENT
--------------------------
The FastAPI app has no direct import of bot.py (that would create a circular
import). Instead, bot.py calls set_discord_client() during on_ready() to hand
over the live discord.Client. This lets us DM users after a successful token
exchange without importing bot.py here.
"""

import logging

import discord
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import exchange_code as _exchange_code

logger = logging.getLogger(__name__)

app = FastAPI()

# Injected by bot.py → on_ready() via set_discord_client().
# None until the Discord bot has fully connected to the gateway, so the DM
# attempt in oauth_callback is guarded by an `if _discord_client:` check.
_discord_client: discord.Client | None = None


def set_discord_client(client: discord.Client) -> None:
    """Called once from bot.py on_ready() to wire up the Discord client.

    This avoids a circular import (bot imports from auth, auth shouldn't import
    from bot). The global is safe here because set_discord_client is called
    exactly once at startup before any OAuth callbacks can arrive.
    """
    global _discord_client
    _discord_client = client


@app.get("/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Handle Google's OAuth2 redirect after user authorisation.

    Query params (set by Google):
      code  — one-time authorisation code, valid for ~10 minutes.
              Exchange it immediately; it cannot be reused.
      state — the Discord user_id we embedded in get_auth_url(); used to
              store the resulting token under the right user.
      error — set by Google if the user denied access or something went wrong
              (e.g. error="access_denied"). We treat any error as a cancellation.

    On success: persists the token via auth.exchange_code, DMs the user, and
    shows a "Connected!" HTML page.
    On failure: returns a 400 or 500 HTML page; the token is NOT stored.
    """
    # Treat missing params or an explicit error param as a cancelled flow.
    if error or not code or not state:
        return HTMLResponse(
            "<h1>Authorization cancelled</h1>"
            "<p>You can close this tab and try again from Discord.</p>",
            status_code=400,
        )

    logger.info("OAuth callback received for user %s", state)
    try:
        _exchange_code(user_id=state, code=code)
    except Exception as e:
        logger.exception("Token exchange failed for user %s", state)
        return HTMLResponse(
            f"<h1>Something went wrong</h1><p>{e}</p>",
            status_code=500,
        )

    if _discord_client:
        try:
            user = await _discord_client.fetch_user(int(state))
            dm = await user.create_dm()
            await dm.send(
                "✅ Google account connected! You can now use all Google Drive features. "
                "Just tell me what you'd like to do."
            )
            logger.info("DM sent to user %s after OAuth", state)
        except Exception:
            logger.warning("Failed to DM user %s after OAuth (non-fatal)", state)

    # This HTML page is shown in the user's browser tab after the redirect.
    return HTMLResponse(
        "<h1>Connected!</h1>"
        "<p>Your Google account is linked. You can close this tab and return to Discord.</p>"
    )
