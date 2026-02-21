"""Per-user OAuth2 token management.

Each Discord user gets their own Google credentials stored under
~/AgentWorkspace/tokens/<discord_user_id>.json.

Tools read the current user's identity from the `current_user_id` ContextVar,
which is set by process_message() in bot.py for every incoming request.
ContextVar values propagate into asyncio.to_thread() workers automatically,
so tools work correctly whether they run sync or async.
"""

import os
import contextvars
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "credentials.json")
TOKENS_DIR = Path.home() / "AgentWorkspace" / "tokens"

# Set once per request in bot.process_message() before invoking the agent.
current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_id", default=""
)


def _token_path(user_id: str) -> Path:
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return TOKENS_DIR / f"{user_id}.json"


def is_authenticated(user_id: str) -> bool:
    return _token_path(user_id).exists()


def get_credentials(user_id: str) -> Optional[Credentials]:
    path = _token_path(user_id)
    if not path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(user_id, creds)
    return creds


def save_credentials(user_id: str, creds: Credentials) -> None:
    _token_path(user_id).write_text(creds.to_json())


def get_auth_url(user_id: str) -> str:
    """Build a Google OAuth2 authorization URL.
    The Discord user_id is embedded as `state` so the callback can map
    the token back to the right user without any server-side session.
    """
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ["OAUTH_REDIRECT_URI"],
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",  # always request consent to guarantee a refresh_token
        state=user_id,
    )
    return url


def exchange_code(user_id: str, code: str) -> Credentials:
    """Exchange an OAuth2 authorization code for credentials and persist them."""
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=os.environ["OAUTH_REDIRECT_URI"],
    )
    flow.fetch_token(code=code)
    save_credentials(user_id, flow.credentials)
    return flow.credentials


def get_docs_service(user_id: str):
    creds = get_credentials(user_id)
    if not creds:
        raise PermissionError(
            "Google account not connected. Send me any message and click 'Connect Google'."
        )
    return build("docs", "v1", credentials=creds)


def get_drive_service(user_id: str):
    creds = get_credentials(user_id)
    if not creds:
        raise PermissionError(
            "Google account not connected. Send me any message and click 'Connect Google'."
        )
    return build("drive", "v3", credentials=creds)
