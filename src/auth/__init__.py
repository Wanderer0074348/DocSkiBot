"""Per-user Google OAuth2 token management.

HOW THE AUTH FLOW WORKS
-----------------------
1. A user DMs the bot for the first time.
2. bot.py calls is_authenticated(user_id) → False.
3. bot.py calls get_auth_url(user_id) and sends a "Connect Google" link button.
4. The user clicks the link → Google consent screen opens in their browser.
5. After the user approves, Google redirects to OAUTH_REDIRECT_URI
   (e.g. https://your-tunnel.trycloudflare.com/oauth/callback?code=...&state=<user_id>).
6. server.py receives the request, calls exchange_code(user_id, code) here,
   which swaps the one-time code for an access + refresh token pair.
7. Credentials are persisted to ~/AgentWorkspace/tokens/<discord_user_id>.json.
8. Future calls to get_credentials() load the token and auto-refresh if expired.

TOKEN STORAGE
-------------
Tokens are plain JSON files, one per Discord user ID, under ~/AgentWorkspace/tokens/.
That directory is Docker-volume-mounted so tokens survive container restarts.
Do NOT commit token files — they grant full Drive/Docs access to the user's account.

IDENTITY PROPAGATION WITH ContextVar
--------------------------------------
Tools are synchronous functions dispatched via asyncio.to_thread(). To avoid
passing user_id as an argument through every call stack layer, we store it in a
contextvars.ContextVar (current_user_id). ContextVar values automatically
propagate from the parent asyncio Task into threads spawned by to_thread(),
so tools always see the correct user without any extra wiring.

  bot.py sets it before invoking the agent:
      token = auth.current_user_id.set(user_id)
      ...
      auth.current_user_id.reset(token)   # restore previous value after

  tools read it:
      user_id = auth.current_user_id.get()
      service = auth.get_docs_service(user_id)

SCOPES
------
Both scopes are requested together in one OAuth grant so the user only has
to click through the consent screen once:
  - documents: read/write Google Docs content
  - drive:     list, delete, and fetch metadata for Drive files

If you need to add more Google APIs later (e.g. Gmail, Calendar), add their
scopes to SCOPES and ask users to re-authorise (delete their token file first).

ADDING A NEW GOOGLE API
-----------------------
1. Add the scope string to SCOPES.
2. Add a get_<service>_service(user_id) function following the pattern below.
3. Import and call it from your tool file (see gdocs.py / gdrive.py).
"""

import logging
import os
import contextvars
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


# ── OAuth2 scopes ─────────────────────────────────────────────────────────────
# Changing these requires users to re-authorise (their existing token will lack
# the new scope and the API will return a 403). To force re-auth, delete their
# token file in TOKENS_DIR or add a /revoke command to the bot.
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

# Path to the OAuth2 Web Application client secrets JSON downloaded from
# Google Cloud Console → APIs & Services → Credentials.
# Default is "credentials.json" in the working directory; override via env var.
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "credentials.json")

# Token files live here. The directory is auto-created on first use.
# In Docker this path is inside the agent_workspace volume, so it persists.
TOKENS_DIR = Path.home() / "AgentWorkspace" / "tokens"

# ── Per-request user identity ─────────────────────────────────────────────────
# Set by process_message() in bot.py for the duration of each agent invocation.
# default="" means any tool that calls .get() before the context is set will
# receive an empty string, which causes get_credentials() to return None and
# the tool to raise a PermissionError with a user-friendly message.
current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_id", default=""
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _token_path(user_id: str) -> Path:
    """Return the path to a user's token file, creating the directory if needed."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return TOKENS_DIR / f"{user_id}.json"


# ── Public API ────────────────────────────────────────────────────────────────

def is_authenticated(user_id: str) -> bool:
    """Return True if a token file exists for this Discord user.

    Note: this only checks file presence, not whether the token is valid or
    still has the right scopes. get_credentials() handles validation and refresh.
    """
    return _token_path(user_id).exists()


def get_credentials(user_id: str) -> Optional[Credentials]:
    """Load credentials from disk, refreshing them if expired.

    Returns None if the user hasn't authenticated yet.
    Saves the refreshed token back to disk so subsequent calls don't need
    to hit the Google token endpoint again.
    """
    path = _token_path(user_id)
    if not path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        logger.info("Refreshing expired token for user %s", user_id)
        creds.refresh(Request())
        save_credentials(user_id, creds)
    return creds


def save_credentials(user_id: str, creds: Credentials) -> None:
    """Persist credentials to disk as JSON (overwrites any existing file)."""
    _token_path(user_id).write_text(creds.to_json())
    logger.info("Credentials saved for user %s", user_id)


def get_auth_url(user_id: str) -> str:
    """Build a Google OAuth2 authorisation URL for a specific Discord user.

    The Discord user_id is embedded as the `state` parameter. Google echoes
    it back verbatim on the callback, so server.py can look up which user
    just authorised without needing any server-side session storage.

    prompt="consent" forces Google to always show the consent screen, which
    guarantees a refresh_token is included in the response. Without this,
    Google only issues a refresh_token on the very first authorisation, so if
    the user revokes and re-authorises without prompt="consent", the token
    exchange would succeed but creds.refresh_token would be None and the token
    would expire after one hour with no way to renew it silently.
    """
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ["OAUTH_REDIRECT_URI"],
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=user_id,
    )
    logger.info("Auth URL generated for user %s", user_id)
    return url


def exchange_code(user_id: str, code: str) -> Credentials:
    """Exchange a one-time OAuth2 authorisation code for credentials and save them.

    Called by server.py immediately after Google redirects to /oauth/callback.
    The `code` is single-use and expires quickly (~10 minutes), so this must
    be called promptly. After this call, the user is considered authenticated.
    """
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ["OAUTH_REDIRECT_URI"],
    )
    flow.fetch_token(code=code)
    logger.info("Code exchanged successfully for user %s", user_id)
    save_credentials(user_id, flow.credentials)
    return flow.credentials


# ── Google API service builders ───────────────────────────────────────────────
# These return ready-to-use API client objects. Tools should call these rather
# than building their own clients so credential loading and error handling
# stay in one place.

def get_docs_service(user_id: str):
    """Return an authenticated Google Docs API v1 client for the given user.

    Raises PermissionError with a user-friendly message if the user hasn't
    connected their Google account yet (so the LLM can relay the message).
    """
    creds = get_credentials(user_id)
    if not creds:
        raise PermissionError(
            "Google account not connected. Send me any message and click 'Connect Google'."
        )
    return build("docs", "v1", credentials=creds)


def get_drive_service(user_id: str):
    """Return an authenticated Google Drive API v3 client for the given user.

    Same error behaviour as get_docs_service(). Used for listing, deleting,
    and fetching file metadata — operations not available in the Docs API.
    """
    creds = get_credentials(user_id)
    if not creds:
        raise PermissionError(
            "Google account not connected. Send me any message and click 'Connect Google'."
        )
    return build("drive", "v3", credentials=creds)
