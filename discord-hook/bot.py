#!/usr/bin/env python3
"""
Emma's Garden Discord Bot
Send messages in Discord to update the gardening project site.

Keywords:
  !garden log <text>        Add a quick update to the session log
  !garden bloom <text>      Report a new bloom or milestone
  !garden photo <url> <cap> Add a photo reference to the gallery
  !garden idea <text>       Add an idea to FUTURE-IDEAS.md
  !garden milestone <text>  Add a row to the milestones table
  !garden status            Show what's pending and in-progress
  !garden help              Show all commands
"""

import os
import re
import sys
import json
import asyncio
import shutil
import aiohttp
import discord
from discord.ext import commands
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "garden-updates")
UPLOADS_CHANNEL_NAME = "garden-uploads"
REPO_PATH = Path(os.getenv("REPO_PATH", Path(__file__).parent.parent))
GIT_PUSH = os.getenv("GIT_PUSH", "true").lower() == "true"

PROGRESS_FILE = REPO_PATH / "PROGRESS-REPORT.md"
IDEAS_FILE = REPO_PATH / "FUTURE-IDEAS.md"
GARDEN_PLAN_FILE = REPO_PATH / "GARDEN-PLAN.md"
RESEARCH_FILE = REPO_PATH / "GARDENING-RESEARCH.md"

# ── Roles & Permissions ───────────────────────────────────────────
# Role names must match the Discord server roles exactly.

ROLE_HEAD_GARDENER = "Head Gardener"
ROLE_GARDEN_HELPER = "Garden Helper"
ROLE_IDEA_PLANTER = "Idea Planter"
ROLE_SPECTATOR = "Spectator"

# Which roles can use which commands
ROLE_PERMISSIONS = {
    "log":       [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER],
    "bloom":     [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER],
    "photo":     [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER],
    "idea":      [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER, ROLE_IDEA_PLANTER],
    "milestone": [ROLE_HEAD_GARDENER],
    "status":    [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER, ROLE_IDEA_PLANTER],
    "ask":       [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER, ROLE_IDEA_PLANTER],
    "diagnose":  [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER],
    "plan":      [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER],
    "help":      [ROLE_HEAD_GARDENER, ROLE_GARDEN_HELPER, ROLE_IDEA_PLANTER, ROLE_SPECTATOR],
}


def has_permission(ctx, command_name: str) -> bool:
    """Check if the user has a role that allows this command."""
    allowed_roles = ROLE_PERMISSIONS.get(command_name, [])
    # Server owner always has access
    if ctx.guild and ctx.author == ctx.guild.owner:
        return True
    user_roles = [r.name for r in ctx.author.roles]
    return any(role in user_roles for role in allowed_roles)


NO_PERMISSION = "You don't have permission for that command. Check your role in the server — see the Contribute page on the site for details!"

# ── Response messages ──────────────────────────────────────────────

RESPONSES = {
    "log_ok":       "Logged! Your garden story grows...",
    "bloom_ok":     "A bloom recorded! How exciting!",
    "photo_ok":     "Photo added to the gallery!",
    "idea_ok":      "Idea planted for later!",
    "milestone_ok": "Milestone added to the tracker!",
    "push_ok":      "Changes pushed — site will update shortly!",
    "push_skip":    "Changes saved locally (auto-push is off).",
    "error":        "Something wilted... {error}",
    "no_text":      "You forgot the message! Try: `!garden {cmd} <your text>`",
}

# ── Git helpers ────────────────────────────────────────────────────

def git_commit_and_push(message: str) -> str:
    """Commit changes and optionally push. Returns status string."""
    try:
        from git import Repo
        repo = Repo(REPO_PATH)
        repo.git.add(A=True)

        if not repo.is_dirty(untracked_files=True):
            return "No changes to commit."

        repo.index.commit(message)

        if GIT_PUSH:
            origin = repo.remote(name="origin")
            origin.push()
            return RESPONSES["push_ok"]
        return RESPONSES["push_skip"]
    except Exception as e:
        return RESPONSES["error"].format(error=str(e))


def today() -> str:
    return datetime.now().strftime("%B %d, %Y")


def today_short() -> str:
    return datetime.now().strftime("%Y-%m-%d")

# ── Local file storage ─────────────────────────────────────────────
# All uploads and command actions get saved locally in discord-hook/uploads/
# so nothing is lost even if Claude, git, or the site breaks.

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
ACTION_LOG_FILE = Path(__file__).parent / "actions.jsonl"


def save_action(user: str, command: str, details: str, files: list = None):
    """Append every action to a local JSONL file as a permanent record."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "command": command,
        "details": details,
        "files": files or [],
    }
    with open(ACTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def download_attachment(attachment: discord.Attachment, subfolder: str = "") -> str:
    """Download a Discord attachment to discord-hook/uploads/. Returns local path."""
    target_dir = UPLOADS_DIR / subfolder if subfolder else UPLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Prefix with timestamp to avoid collisions
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = re.sub(r'[^\w.\-]', '_', attachment.filename)
    local_path = target_dir / f"{ts}_{safe_name}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status == 200:
                    local_path.write_bytes(await resp.read())
                    return str(local_path)
    except Exception as e:
        print(f"Failed to download {attachment.filename}: {e}")

    return ""


# ── File update helpers ────────────────────────────────────────────

def append_log_entry(text: str) -> bool:
    """Append a quick log entry under the latest session in PROGRESS-REPORT.md."""
    content = PROGRESS_FILE.read_text(encoding="utf-8")

    entry = f"\n**Discord Update — {today()}:** {text}\n"

    # Insert before "## What's Done So Far"
    marker = "## What's Done So Far"
    if marker in content:
        content = content.replace(marker, entry + "\n" + marker)
    else:
        content += entry

    PROGRESS_FILE.write_text(content, encoding="utf-8")
    return True


def add_milestone(text: str) -> bool:
    """Add a row to the milestones table in PROGRESS-REPORT.md."""
    content = PROGRESS_FILE.read_text(encoding="utf-8")

    row = f"| {today()} | {text} | Done |\n"

    # Find the last row of the milestones table (line starting with |)
    lines = content.split("\n")
    insert_idx = None
    in_milestones = False
    for i, line in enumerate(lines):
        if "| Date | Milestone | Status |" in line:
            in_milestones = True
        if in_milestones and line.startswith("|"):
            insert_idx = i + 1
        if in_milestones and not line.startswith("|") and line.strip() and insert_idx:
            break

    if insert_idx:
        lines.insert(insert_idx, row.rstrip())
        PROGRESS_FILE.write_text("\n".join(lines), encoding="utf-8")
        return True
    return False


def add_bloom(text: str) -> bool:
    """Record a bloom as both a log entry and a milestone."""
    append_log_entry(f"NEW BLOOM! {text}")
    add_milestone(f"Bloom: {text}")
    return True


def add_photo(url: str, caption: str) -> bool:
    """Add a photo entry to the Photo Log table in PROGRESS-REPORT.md."""
    content = PROGRESS_FILE.read_text(encoding="utf-8")

    row = f"| {today()} | {caption} | ![photo]({url}) |\n"

    lines = content.split("\n")
    insert_idx = None
    in_photo_log = False
    for i, line in enumerate(lines):
        if "| Date | Description | Photo |" in line:
            in_photo_log = True
        if in_photo_log and line.strip().startswith("| ") and "coming soon" in line.lower():
            insert_idx = i
            break
        if in_photo_log and line.startswith("|"):
            insert_idx = i + 1

    if insert_idx:
        lines.insert(insert_idx, row.rstrip())
        PROGRESS_FILE.write_text("\n".join(lines), encoding="utf-8")
        return True
    return False


def add_idea(text: str) -> bool:
    """Append an idea to FUTURE-IDEAS.md."""
    content = IDEAS_FILE.read_text(encoding="utf-8")

    # Add under "Fun Project Ideas" section, before the seasonal roadmap
    marker = "## Seasonal Expansion Roadmap"
    entry = f"\n### Discord Idea ({today()})\n{text}\n\n"

    if marker in content:
        content = content.replace(marker, entry + marker)
    else:
        content += entry

    IDEAS_FILE.write_text(content, encoding="utf-8")
    return True


def get_status() -> str:
    """Parse PROGRESS-REPORT.md and return pending/in-progress items."""
    content = PROGRESS_FILE.read_text(encoding="utf-8")

    pending = []
    in_progress = []

    for line in content.split("\n"):
        stripped = line.strip()
        if "| Pending" in stripped or "| Pending |" in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if len(parts) >= 2:
                pending.append(parts[1])
        if "| In Progress" in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if len(parts) >= 2:
                in_progress.append(parts[1])
        if stripped.startswith("- ") and "Pending" in stripped:
            pending.append(stripped.lstrip("- ").replace("— Pending", "").strip())
        if stripped.startswith("- ") and "In Progress" in stripped:
            in_progress.append(stripped.lstrip("- ").replace("— In Progress", "").strip())

    # Also grab "In Progress" and "Not Yet Started" sections
    sections = {"in_progress": [], "not_started": []}
    current = None
    for line in content.split("\n"):
        if "### In Progress" in line:
            current = "in_progress"
            continue
        elif "### Not Yet Started" in line:
            current = "not_started"
            continue
        elif line.startswith("### ") or line.startswith("## "):
            current = None
            continue
        if current and line.strip().startswith("- "):
            sections[current].append(line.strip().lstrip("- "))

    status_lines = ["**Emma's Garden Status**\n"]

    if sections["in_progress"] or in_progress:
        status_lines.append("**In Progress:**")
        for item in (sections["in_progress"] or in_progress):
            status_lines.append(f"  - {item}")

    if sections["not_started"]:
        status_lines.append("\n**Not Yet Started:**")
        for item in sections["not_started"]:
            status_lines.append(f"  - {item}")

    if pending:
        status_lines.append("\n**Pending Milestones:**")
        for item in pending:
            status_lines.append(f"  - {item}")

    return "\n".join(status_lines) if len(status_lines) > 1 else "Everything's on track! Nothing pending."

# ── Claude AI helpers ──────────────────────────────────────────────

def get_garden_context() -> str:
    """Build a context string from the garden files so Claude knows Emma's setup."""
    context_parts = []

    for filepath, label in [
        (PROGRESS_FILE, "Progress Report"),
        (GARDEN_PLAN_FILE, "Garden Plan"),
        (IDEAS_FILE, "Future Ideas"),
    ]:
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            # Truncate long files to keep token usage reasonable
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            context_parts.append(f"## {label}\n{content}")

    return "\n\n---\n\n".join(context_parts)


GARDEN_SYSTEM_PROMPT = """You are Emma's Garden Bot — a friendly, knowledgeable gardening assistant \
embedded in a Discord server for Emma's balcony flower garden in Stuttgart, Germany (Zone 7b/8a).

Emma is a first-time gardener who started in April 2026 with a sunny balcony, some seeds, bulbs, \
and a lot of enthusiasm. Your job is to give helpful, encouraging, and practical gardening advice \
tailored to her specific setup.

Key facts:
- Location: Stuttgart, Germany — sunny balcony
- Climate zone: 7b/8a, continental with warm summers
- Experience level: complete beginner
- Current date context: answers should be seasonally appropriate

Keep answers concise (under 300 words) since they'll appear in Discord. Be warm and encouraging \
but practical. Use simple language — no jargon without explanation. If you mention a product or \
technique, explain why it helps.

Below is the current state of Emma's garden:

{context}
"""


CLAUDE_CLI = os.getenv("CLAUDE_CLI_PATH", shutil.which("claude") or "claude")


async def ask_claude(question: str, system_extra: str = "") -> str:
    """Send a question to the local Claude CLI (uses your existing OAuth login)."""
    claude_path = shutil.which("claude") if CLAUDE_CLI == "claude" else CLAUDE_CLI
    if not claude_path:
        return ("Claude CLI not found on this machine. "
                "Install it with: `npm install -g @anthropic-ai/claude-code`")

    context = get_garden_context()
    system = GARDEN_SYSTEM_PROMPT.format(context=context)
    if system_extra:
        system += f"\n\n{system_extra}"

    try:
        proc = await asyncio.create_subprocess_exec(
            claude_path, "-p",
            "--system-prompt", system,
            "--output-format", "text",
            "--max-turns", "1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=question.encode("utf-8")),
            timeout=60,
        )

        if proc.returncode == 0 and stdout:
            return stdout.decode("utf-8").strip()
        elif stderr:
            err = stderr.decode("utf-8").strip()
            return f"Claude had trouble answering: {err[:200]}"
        else:
            return "Claude returned an empty response — try again?"
    except asyncio.TimeoutError:
        return "Claude took too long to respond (60s timeout). Try a simpler question?"
    except Exception as e:
        return f"Couldn't reach Claude: {e}"


async def send_long_message(ctx, text: str):
    """Split long messages to stay under Discord's 2000-char limit."""
    while text:
        if len(text) <= 2000:
            await ctx.send(text)
            break
        # Find a good split point
        split_at = text.rfind("\n", 0, 2000)
        if split_at == -1:
            split_at = 2000
        await ctx.send(text[:split_at])
        text = text[split_at:].lstrip("\n")


# ── Bot setup ──────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Garden bot is online as {bot.user}")

    if GUILD_ID:
        guild = bot.get_guild(int(GUILD_ID))
        if guild:
            # Create channel if it doesn't exist
            # Create #garden-updates if needed
            existing = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
            if not existing:
                try:
                    channel = await guild.create_text_channel(
                        CHANNEL_NAME,
                        topic="Send garden updates here! Use !garden help to see commands.",
                    )
                    print(f"Created #{CHANNEL_NAME} in {guild.name}")
                    await channel.send(
                        "**Emma's Garden Bot is live!**\n\n"
                        "Send updates here and they'll appear on the garden website.\n"
                        "Type `!garden help` to see all commands."
                    )
                except discord.Forbidden:
                    print(f"Missing permissions to create #{CHANNEL_NAME}")
            else:
                print(f"#{CHANNEL_NAME} already exists in {guild.name}")

            # Create #garden-uploads if needed
            uploads_ch = discord.utils.get(guild.text_channels, name=UPLOADS_CHANNEL_NAME)
            if not uploads_ch:
                try:
                    uploads_ch = await guild.create_text_channel(
                        UPLOADS_CHANNEL_NAME,
                        topic="Drop photos, ideas, and anything garden-related here! The bot logs everything.",
                    )
                    print(f"Created #{UPLOADS_CHANNEL_NAME} in {guild.name}")
                    await uploads_ch.send(
                        "**Garden Uploads**\n\n"
                        "Drop your garden photos, plant finds, and ideas here!\n"
                        "The bot will log who posted what and when.\n"
                        "Attach images or just type — everything gets recorded."
                    )
                except discord.Forbidden:
                    print(f"Missing permissions to create #{UPLOADS_CHANNEL_NAME}")
            else:
                print(f"#{UPLOADS_CHANNEL_NAME} already exists in {guild.name}")


HELP_TEXT = """
**Emma's Garden Bot - Commands**

**Update the Site:**
| Command | What it does |
|---------|-------------|
| `!garden log <text>` | Add a quick update to the session log |
| `!garden bloom <text>` | Record a new bloom or milestone event |
| `!garden photo <url> <caption>` | Add a photo to the gallery |
| `!garden idea <text>` | Add an idea to the Future Ideas page |
| `!garden milestone <text>` | Add a milestone to the tracker |
| `!garden status` | Show pending and in-progress tasks |

**Ask Claude AI:**
| Command | What it does |
|---------|-------------|
| `!garden ask <question>` | Ask a gardening question — Claude knows your garden! |
| `!garden diagnose <symptoms>` | Describe a plant problem and get diagnosis + fix |
| `!garden plan` | Get personalized advice for what to do this week |

**Examples:**
```
!garden log Sprouts appeared in cells 3 and 7 today!
!garden bloom First cosmos flower opened — bright pink!
!garden ask When should I start hardening off my seedlings?
!garden diagnose My basil leaves are turning yellow at the bottom
!garden plan
```
""".strip()


@bot.group(name="garden", invoke_without_command=True)
async def garden(ctx):
    await ctx.send(HELP_TEXT)


@garden.command(name="help")
async def garden_help(ctx):
    await ctx.send(HELP_TEXT)


@garden.command(name="log")
async def garden_log(ctx, *, text: str = None):
    if not has_permission(ctx, "log"):
        await ctx.send(NO_PERMISSION)
        return
    if not text:
        await ctx.send(RESPONSES["no_text"].format(cmd="log"))
        return
    # Always save locally first — this never fails
    saved_files = []
    for att in ctx.message.attachments:
        path = await download_attachment(att, "logs")
        if path:
            saved_files.append(path)
    save_action(ctx.author.display_name, "!garden log", text, saved_files)

    try:
        append_log_entry(text)
        log_command(ctx.author.display_name, "!garden log", text)
        result = git_commit_and_push(f"Discord update: {text[:60]}")
        await ctx.send(f"{RESPONSES['log_ok']}\n> {text}\n\n_{result}_")
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


@garden.command(name="bloom")
async def garden_bloom(ctx, *, text: str = None):
    if not has_permission(ctx, "bloom"):
        await ctx.send(NO_PERMISSION)
        return
    if not text:
        await ctx.send(RESPONSES["no_text"].format(cmd="bloom"))
        return

    saved_files = []
    for att in ctx.message.attachments:
        path = await download_attachment(att, "blooms")
        if path:
            saved_files.append(path)
    save_action(ctx.author.display_name, "!garden bloom", text, saved_files)

    try:
        add_bloom(text)
        log_command(ctx.author.display_name, "!garden bloom", text)
        result = git_commit_and_push(f"New bloom: {text[:60]}")
        await ctx.send(f"{RESPONSES['bloom_ok']}\n> {text}\n\n_{result}_")
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


@garden.command(name="photo")
async def garden_photo(ctx, url: str = None, *, caption: str = None):
    if not has_permission(ctx, "photo"):
        await ctx.send(NO_PERMISSION)
        return
    if not url or not caption:
        await ctx.send("Usage: `!garden photo <image-url> <caption>`")
        return

    saved_files = []
    for att in ctx.message.attachments:
        path = await download_attachment(att, "photos")
        if path:
            saved_files.append(path)
    save_action(ctx.author.display_name, "!garden photo", f"{url} — {caption}", saved_files)

    try:
        add_photo(url, caption)
        log_command(ctx.author.display_name, "!garden photo", f"{url} — {caption}")
        result = git_commit_and_push(f"Photo added: {caption[:60]}")
        await ctx.send(f"{RESPONSES['photo_ok']}\n> {caption}\n\n_{result}_")
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


@garden.command(name="idea")
async def garden_idea(ctx, *, text: str = None):
    if not has_permission(ctx, "idea"):
        await ctx.send(NO_PERMISSION)
        return
    if not text:
        await ctx.send(RESPONSES["no_text"].format(cmd="idea"))
        return

    saved_files = []
    for att in ctx.message.attachments:
        path = await download_attachment(att, "ideas")
        if path:
            saved_files.append(path)
    save_action(ctx.author.display_name, "!garden idea", text, saved_files)

    try:
        add_idea(text)
        log_command(ctx.author.display_name, "!garden idea", text)
        result = git_commit_and_push(f"New idea: {text[:60]}")
        await ctx.send(f"{RESPONSES['idea_ok']}\n> {text}\n\n_{result}_")
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


@garden.command(name="milestone")
async def garden_milestone(ctx, *, text: str = None):
    if not has_permission(ctx, "milestone"):
        await ctx.send(NO_PERMISSION)
        return
    if not text:
        await ctx.send(RESPONSES["no_text"].format(cmd="milestone"))
        return

    save_action(ctx.author.display_name, "!garden milestone", text)

    try:
        add_milestone(text)
        log_command(ctx.author.display_name, "!garden milestone", text)
        result = git_commit_and_push(f"Milestone: {text[:60]}")
        await ctx.send(f"{RESPONSES['milestone_ok']}\n> {text}\n\n_{result}_")
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


@garden.command(name="status")
async def garden_status(ctx):
    if not has_permission(ctx, "status"):
        await ctx.send(NO_PERMISSION)
        return
    try:
        status = get_status()
        await ctx.send(status)
    except Exception as e:
        await ctx.send(RESPONSES["error"].format(error=str(e)))


# ── Upload channel listener ────────────────────────────────────────

UPLOADS_LOG = REPO_PATH / "DISCORD-LOG.md"


def ensure_log_file():
    """Create the Discord log markdown file if it doesn't exist."""
    if not UPLOADS_LOG.exists():
        UPLOADS_LOG.write_text(
            "---\nlayout: default\ntitle: Discord Log\npermalink: /DISCORD-LOG\n---\n\n"
            "# Discord Log\n\n"
            "**All bot commands and uploads from the Discord server.**\n\n---\n\n"
            "## Uploads\n\n"
            "| Date | User | Type | Content |\n"
            "|------|------|------|---------|\n\n"
            "---\n\n"
            "## Command History\n\n"
            "| Date | User | Command | Details |\n"
            "|------|------|---------|--------|\n",
            encoding="utf-8",
        )


def log_command(user: str, command: str, details: str):
    """Log a bot command to DISCORD-LOG.md."""
    ensure_log_file()
    content = UPLOADS_LOG.read_text(encoding="utf-8")

    row = f"| {today()} | {user} | `{command}` | {details[:100]} |"

    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "| Date | User | Command | Details |" in line:
            # Insert after the header separator (2 lines down)
            insert_at = i + 2
            lines.insert(insert_at, row)
            break

    UPLOADS_LOG.write_text("\n".join(lines), encoding="utf-8")


def log_upload(user: str, upload_type: str, content_text: str):
    """Log an upload to DISCORD-LOG.md."""
    ensure_log_file()
    content = UPLOADS_LOG.read_text(encoding="utf-8")

    row = f"| {today()} | {user} | {upload_type} | {content_text[:100]} |"

    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "| Date | User | Type | Content |" in line:
            insert_at = i + 2
            lines.insert(insert_at, row)
            break

    UPLOADS_LOG.write_text("\n".join(lines), encoding="utf-8")


@bot.event
async def on_message(message):
    # Don't respond to ourselves
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    # Log uploads in #garden-uploads
    if message.channel.name == UPLOADS_CHANNEL_NAME:
        user = message.author.display_name
        saved_files = []

        if message.attachments:
            for att in message.attachments:
                # Download locally first — always works
                path = await download_attachment(att, "channel-uploads")
                if path:
                    saved_files.append(path)
                caption = message.content or "No caption"
                log_upload(user, "Photo", f"[{att.filename}]({att.url}) — {caption}")
                await message.add_reaction("\u2705")  # checkmark
        elif message.content:
            log_upload(user, "Message", message.content)
            await message.add_reaction("\U0001F331")  # seedling

        save_action(user, "#garden-uploads", message.content or "(attachment only)", saved_files)
        git_commit_and_push(f"Discord upload from {user}")

    await bot.process_commands(message)


# ── Claude AI commands ─────────────────────────────────────────────

@garden.command(name="ask")
async def garden_ask(ctx, *, question: str = None):
    if not has_permission(ctx, "ask"):
        await ctx.send(NO_PERMISSION)
        return
    if not question:
        await ctx.send("Ask me anything! Example: `!garden ask How often should I water my cosmos seedlings?`")
        return
    save_action(ctx.author.display_name, "!garden ask", question)
    async with ctx.typing():
        log_command(ctx.author.display_name, "!garden ask", question)
        answer = await ask_claude(question)
    await send_long_message(ctx, answer)


@garden.command(name="diagnose")
async def garden_diagnose(ctx, *, symptoms: str = None):
    if not has_permission(ctx, "diagnose"):
        await ctx.send(NO_PERMISSION)
        return
    if not symptoms:
        await ctx.send("Describe the problem! Example: `!garden diagnose My basil leaves are turning yellow and drooping`")
        return

    saved_files = []
    for att in ctx.message.attachments:
        path = await download_attachment(att, "diagnose")
        if path:
            saved_files.append(path)
    save_action(ctx.author.display_name, "!garden diagnose", symptoms, saved_files)

    async with ctx.typing():
        log_command(ctx.author.display_name, "!garden diagnose", symptoms)
        answer = await ask_claude(
            f"My plant has this problem: {symptoms}",
            system_extra=(
                "The user is describing a plant problem. Respond with:\n"
                "1. What's likely wrong (most probable cause first)\n"
                "2. How to fix it — simple, actionable steps\n"
                "3. How to prevent it next time\n"
                "Be reassuring — beginners panic easily. If it sounds minor, say so."
            ),
        )
    await send_long_message(ctx, answer)


@garden.command(name="plan")
async def garden_plan(ctx):
    if not has_permission(ctx, "plan"):
        await ctx.send(NO_PERMISSION)
        return

    save_action(ctx.author.display_name, "!garden plan", "Weekly plan request")

    async with ctx.typing():
        now = datetime.now()
        log_command(ctx.author.display_name, "!garden plan", f"Weekly plan for {now.strftime('%B %d')}")
        answer = await ask_claude(
            f"It's {now.strftime('%B %d, %Y')}. Based on my garden's current state, "
            f"what should I be doing this week? Give me a short to-do list.",
            system_extra=(
                "Give a personalized weekly to-do list based on:\n"
                "- The current date and season in Stuttgart\n"
                "- What's currently planted and its growth stage\n"
                "- Any pending tasks from the progress report\n"
                "Keep it to 5-7 actionable items. Be specific, not generic."
            ),
        )
    await send_long_message(ctx, answer)


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set in .env file")
        print("Run 'python setup.py' to configure the bot first.")
        sys.exit(1)
    bot.run(TOKEN)
