import os
import discord

from .. import auth
from ..auth.server import set_discord_client
from . import picker as picker_module
from . import forms as forms_module


# ── Intents ───────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# Optional allowlist. Set ALLOWED_DISCORD_USER_IDS to a comma-separated list of
# Discord user IDs. If unset or empty, the bot responds to anyone in DMs.
_raw = os.environ.get("ALLOWED_DISCORD_USER_IDS", "")
ALLOWED_USER_IDS: set[int] = (
    {int(uid.strip()) for uid in _raw.split(",") if uid.strip()}
    if _raw.strip() else set()
)


# ── Discord UI — Google auth link button ──────────────────────────────────────

class GoogleAuthView(discord.ui.View):
    """Sends a link button that opens the Google OAuth2 consent screen."""

    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Connect Google",
            url=url,
            style=discord.ButtonStyle.link,
            emoji="🔗",
        ))


# ── Discord UI — Document picker select menu ──────────────────────────────────

class DocumentPickerView(discord.ui.View):
    """Shows a Select menu with up to 25 Google Docs. On selection, injects
    the chosen document back into the agent as a new message.
    """

    def __init__(self, docs: list[dict], user_id: str, channel: discord.abc.Messageable):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.channel = channel

        options = [
            discord.SelectOption(
                label=d["name"][:100],
                value=d["id"],
                description=f"Modified {d.get('modifiedTime', '')[:10]}",
            )
            for d in docs[:25]
        ]
        select = discord.ui.Select(placeholder="Choose a document…", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This picker isn't for you.", ephemeral=True)
            return

        selected_id = interaction.data["values"][0]
        selected_name = next(
            (o.label for o in self.children[0].options if o.value == selected_id),
            selected_id,
        )
        # Disable the select so it can't be reused.
        self.children[0].disabled = True
        await interaction.response.edit_message(view=self)

        await process_message(
            self.user_id,
            f"[Document selected] name: {selected_name}, id: {selected_id}",
            self.channel,
        )


# ── Discord UI — Form modal & button (from forms.py) ─────────────────────────

class AgentFormModal(discord.ui.Modal):
    def __init__(self, form_def: dict, user_id: str, channel: discord.abc.Messageable):
        super().__init__(title=form_def["title"])
        self.user_id = user_id
        self.channel = channel
        for field in form_def["fields"]:
            self.add_item(discord.ui.TextInput(
                label=field["label"],
                placeholder=field.get("placeholder", ""),
                style=discord.TextStyle.long if field.get("long") else discord.TextStyle.short,
                required=True,
            ))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = "\n".join(
            f"{item.label}: {item.value}"
            for item in self.children
            if isinstance(item, discord.ui.TextInput)
        )
        await interaction.response.defer()
        await process_message(self.user_id, f"[Form submitted]\n{answers}", self.channel)


class FormButtonView(discord.ui.View):
    def __init__(self, form_def: dict, user_id: str, channel: discord.abc.Messageable):
        super().__init__(timeout=300)
        self.form_def = form_def
        self.user_id = user_id
        self.channel = channel

    @discord.ui.button(label="Open Form", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This form isn't for you.", ephemeral=True)
            return
        modal = AgentFormModal(
            form_def=self.form_def,
            user_id=self.user_id,
            channel=self.channel,
        )
        await interaction.response.send_modal(modal)
        button.disabled = True
        await interaction.message.edit(view=self)


# ── Core agent invocation ─────────────────────────────────────────────────────

async def process_message(user_id: str, content: str, channel: discord.abc.Messageable) -> None:
    """Run the agent for a user message and dispatch any queued UI components."""
    # Lazy import to avoid circular deps at module load time.
    from .agent import agent

    # Gate: if the user hasn't connected Google yet, send the auth link instead.
    if not auth.is_authenticated(user_id):
        url = auth.get_auth_url(user_id)
        await channel.send(
            "First, connect your Google account so I can access your Drive:",
            view=GoogleAuthView(url),
        )
        return

    # Stamp the current user into the async context so tools know whose
    # credentials to use (propagates into asyncio.to_thread workers too).
    token = auth.current_user_id.set(user_id)

    async with channel.typing():
        try:
            result = await agent.ainvoke(
                {"messages": [("human", content)], "user_id": user_id},
                config={"configurable": {"thread_id": user_id}},
            )
            reply = str(result["messages"][-1].content)
        except Exception as e:
            reply = f"Something went wrong and I couldn't complete that: {e}"
        finally:
            auth.current_user_id.reset(token)

    # Check for any UI components the agent queued during its run.
    pending_form = forms_module.pop_pending_form()
    pending_picker = picker_module.pop_pending_picker()

    chunks = _split(reply)
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        if is_last and pending_picker:
            view = DocumentPickerView(docs=pending_picker, user_id=user_id, channel=channel)
            await channel.send(chunk, view=view)
        elif is_last and pending_form:
            view = FormButtonView(form_def=pending_form, user_id=user_id, channel=channel)
            await channel.send(chunk, view=view)
        else:
            await channel.send(chunk)


# ── Event handlers ────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f"Agent online as {client.user} (ID: {client.user.id})")
    set_discord_client(client)  # wire into OAuth callback server for DMs


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return
    if ALLOWED_USER_IDS and message.author.id not in ALLOWED_USER_IDS:
        return

    await process_message(str(message.author.id), message.content, message.channel)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split(text: str, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + limit])
        start += limit
    return chunks
