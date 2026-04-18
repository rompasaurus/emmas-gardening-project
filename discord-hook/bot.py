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
import discord
from discord.ext import commands
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "garden-updates")
REPO_PATH = Path(os.getenv("REPO_PATH", Path(__file__).parent.parent))
GIT_PUSH = os.getenv("GIT_PUSH", "true").lower() == "true"

PROGRESS_FILE = REPO_PATH / "PROGRESS-REPORT.md"
IDEAS_FILE = REPO_PATH / "FUTURE-IDEAS.md"

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


HELP_TEXT = """
**Emma's Garden Bot - Commands**

| Command | What it does |
|---------|-------------|
| `!garden log <text>` | Add a quick update to the session log |
| `!garden bloom <text>` | Record a new bloom or milestone event |
| `!garden photo <url> <caption>` | Add a photo to the gallery |
| `!garden idea <text>` | Add an idea to the Future Ideas page |
| `!garden milestone <text>` | Add a milestone to the tracker |
| `!garden status` | Show pending and in-progress tasks |
| `!garden help` | Show this message |

**Examples:**
```
!garden log Sprouts appeared in cells 3 and 7 today!
!garden bloom First cosmos flower opened — bright pink!
!garden photo https://i.imgur.com/abc.jpg The first zinnia bloom
!garden idea Try growing strawberries in a hanging basket
!garden milestone Transplanted seedlings to balcony pots
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
    try:
        append_log_entry(text)
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
    try:
        add_bloom(text)
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
    try:
        add_photo(url, caption)
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
    try:
        add_idea(text)
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
    try:
        add_milestone(text)
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


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set in .env file")
        print("Run 'python setup.py' to configure the bot first.")
        sys.exit(1)
    bot.run(TOKEN)
