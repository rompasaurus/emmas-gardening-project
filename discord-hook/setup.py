#!/usr/bin/env python3
"""
Emma's Garden Bot — Setup Wizard
Interactive CLI to install dependencies, configure the bot, and get everything running.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"
ENV_EXAMPLE = SCRIPT_DIR / ".env.example"
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
REPO_PATH = SCRIPT_DIR.parent

# ── Pretty printing ────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"


def banner():
    print(f"""
{GREEN}{BOLD}
    .-~~-.
   {{      }}
    `-..-'        Emma's Garden Bot
      ||          ─────────────────
      ||          Discord Setup Wizard
     _||_
    {{____}}
{RESET}""")


def header(text):
    print(f"\n{CYAN}{BOLD}{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}{RESET}\n")


def success(text):
    print(f"  {GREEN}[OK]{RESET} {text}")


def warn(text):
    print(f"  {YELLOW}[!!]{RESET} {text}")


def error(text):
    print(f"  {RED}[ERR]{RESET} {text}")


def info(text):
    print(f"  {DIM}[..]{RESET} {text}")


def prompt(text, default=None):
    if default:
        val = input(f"  {BOLD}{text}{RESET} [{default}]: ").strip()
        return val if val else default
    return input(f"  {BOLD}{text}{RESET}: ").strip()

# ── Menu actions ───────────────────────────────────────────────────

def install_dependencies():
    header("Step 1: Install Python Dependencies")

    python = sys.executable
    info(f"Using Python: {python}")

    # Check for venv
    venv_path = SCRIPT_DIR / "venv"
    if not venv_path.exists():
        answer = prompt("Create a virtual environment? (recommended) [y/n]", "y")
        if answer.lower() == "y":
            info("Creating virtual environment...")
            subprocess.run([python, "-m", "venv", str(venv_path)], check=True)
            success("Virtual environment created at fun/venv/")

            if os.name == "nt":
                pip = str(venv_path / "Scripts" / "pip")
            else:
                pip = str(venv_path / "bin" / "pip")
        else:
            pip = "pip"
    else:
        success("Virtual environment already exists")
        if os.name == "nt":
            pip = str(venv_path / "Scripts" / "pip")
        else:
            pip = str(venv_path / "bin" / "pip")

    info("Installing dependencies...")
    result = subprocess.run(
        [pip, "install", "-r", str(REQUIREMENTS)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        success("All dependencies installed!")
        for line in result.stdout.split("\n"):
            if "Successfully installed" in line:
                info(line.strip())
    else:
        error("Installation failed:")
        print(result.stderr)
        return False
    return True


def configure_bot():
    header("Step 2: Configure Discord Bot")

    print(f"""  {MAGENTA}Before we start, you'll need a Discord bot token.{RESET}
  If you don't have one yet, here's how:

  {BOLD}1.{RESET} Go to {CYAN}https://discord.com/developers/applications{RESET}
  {BOLD}2.{RESET} Click "New Application" — name it "Emma's Garden Bot"
  {BOLD}3.{RESET} Go to the "Bot" tab on the left
  {BOLD}4.{RESET} Click "Reset Token" and copy the token
  {BOLD}5.{RESET} Under "Privileged Gateway Intents", enable:
     - {BOLD}MESSAGE CONTENT INTENT{RESET} (required!)
  {BOLD}6.{RESET} Go to "OAuth2" > "URL Generator"
     - Scopes: {BOLD}bot{RESET}
     - Permissions: {BOLD}Send Messages, Read Messages, Manage Channels{RESET}
  {BOLD}7.{RESET} Copy the generated URL and open it to invite the bot
""")

    token = prompt("Paste your Discord bot token")
    if not token:
        error("Token is required!")
        return False

    guild_id = prompt("Your Discord server (guild) ID\n  (Right-click server name > Copy Server ID — enable Developer Mode in Discord settings)")
    if not guild_id:
        error("Guild ID is required!")
        return False

    channel_name = prompt("Channel name for garden updates", "garden-updates")
    repo_path = prompt("Path to the garden project repo", str(REPO_PATH))
    git_push = prompt("Auto-push to GitHub after updates? [y/n]", "y")

    env_content = f"""DISCORD_BOT_TOKEN={token}
GUILD_ID={guild_id}
CHANNEL_NAME={channel_name}
REPO_PATH={repo_path}
GIT_PUSH={'true' if git_push.lower() == 'y' else 'false'}
"""

    ENV_FILE.write_text(env_content)
    success(f"Configuration saved to {ENV_FILE.name}")
    warn("This file contains your bot token — it's already in .gitignore")
    return True


def show_commands():
    header("Bot Commands Reference")

    print(f"""  {BOLD}Keyword Commands{RESET} — type these in #{CYAN}garden-updates{RESET}

  {GREEN}!garden log <text>{RESET}
    Add a quick update to the session log.
    Example: {DIM}!garden log Sprouts appeared in cells 3 and 7!{RESET}
    Bot responds: {DIM}Logged! Your garden story grows...{RESET}

  {GREEN}!garden bloom <text>{RESET}
    Record a new bloom — adds to both log and milestones.
    Example: {DIM}!garden bloom First cosmos flower opened — bright pink!{RESET}
    Bot responds: {DIM}A bloom recorded! How exciting!{RESET}

  {GREEN}!garden photo <url> <caption>{RESET}
    Add a photo to the Photo Log table.
    Example: {DIM}!garden photo https://i.imgur.com/abc.jpg The first zinnia bloom{RESET}
    Bot responds: {DIM}Photo added to the gallery!{RESET}

  {GREEN}!garden idea <text>{RESET}
    Add an idea to FUTURE-IDEAS.md for later.
    Example: {DIM}!garden idea Try growing strawberries in a hanging basket{RESET}
    Bot responds: {DIM}Idea planted for later!{RESET}

  {GREEN}!garden milestone <text>{RESET}
    Add a completed milestone to the tracker.
    Example: {DIM}!garden milestone Transplanted all seedlings to balcony{RESET}
    Bot responds: {DIM}Milestone added to the tracker!{RESET}

  {GREEN}!garden status{RESET}
    See what's pending and in-progress.
    Bot responds with a formatted status report.

  {GREEN}!garden help{RESET}
    Show the command list inside Discord.

  {BOLD}On Success:{RESET} Bot confirms the action + shows git push status.
  {BOLD}On Failure:{RESET} Bot replies with "Something wilted... <error details>"
""")


def test_bot():
    header("Test Bot Connection")

    if not ENV_FILE.exists():
        error("No .env file found — run Configure first!")
        return

    venv_python = SCRIPT_DIR / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    info("Starting bot (press Ctrl+C to stop)...")
    print()
    try:
        subprocess.run([python, str(SCRIPT_DIR / "bot.py")])
    except KeyboardInterrupt:
        print()
        success("Bot stopped.")


def run_bot_background():
    header("Run Bot in Background")

    if not ENV_FILE.exists():
        error("No .env file found — run Configure first!")
        return

    venv_python = SCRIPT_DIR / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    info("Starting bot in background...")

    pid_file = SCRIPT_DIR / "bot.pid"

    # Check if already running
    if pid_file.exists():
        old_pid = pid_file.read_text().strip()
        try:
            os.kill(int(old_pid), 0)
            warn(f"Bot already running (PID {old_pid})")
            answer = prompt("Kill and restart? [y/n]", "n")
            if answer.lower() == "y":
                os.kill(int(old_pid), 9)
                info(f"Killed PID {old_pid}")
            else:
                return
        except (OSError, ValueError):
            pass  # Process not running

    log_file = SCRIPT_DIR / "bot.log"
    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            [python, str(SCRIPT_DIR / "bot.py")],
            stdout=log, stderr=log,
            start_new_session=True,
        )
    pid_file.write_text(str(proc.pid))
    success(f"Bot started in background (PID {proc.pid})")
    info(f"Logs: {log_file}")
    info(f"Stop with: kill {proc.pid}")


def stop_bot():
    header("Stop Background Bot")

    pid_file = SCRIPT_DIR / "bot.pid"
    if not pid_file.exists():
        warn("No bot.pid file found — bot may not be running")
        return

    pid = pid_file.read_text().strip()
    try:
        os.kill(int(pid), 15)  # SIGTERM
        success(f"Sent stop signal to PID {pid}")
        pid_file.unlink()
    except (OSError, ValueError) as e:
        warn(f"Could not stop process: {e}")
        pid_file.unlink()


def full_setup():
    """Run all setup steps in order."""
    banner()
    print(f"  {BOLD}Full setup will walk you through everything.{RESET}\n")

    if not install_dependencies():
        error("Dependency installation failed. Fix errors above and retry.")
        return

    print()
    if not configure_bot():
        error("Configuration incomplete. Run setup again when ready.")
        return

    print()
    show_commands()

    print(f"\n  {GREEN}{BOLD}Setup complete!{RESET}")
    print(f"  Run the bot with: {CYAN}python setup.py{RESET} > option 5 or 6\n")


def check_status():
    header("Current Status")

    # Check venv
    venv_path = SCRIPT_DIR / "venv"
    if venv_path.exists():
        success("Virtual environment: installed")
    else:
        warn("Virtual environment: not created")

    # Check .env
    if ENV_FILE.exists():
        success(".env config: exists")
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
        token = os.getenv("DISCORD_BOT_TOKEN", "")
        if token and token != "your-bot-token-here":
            success(f"Bot token: configured ({token[:8]}...)")
        else:
            warn("Bot token: not set")
        guild = os.getenv("GUILD_ID", "")
        if guild:
            success(f"Guild ID: {guild}")
        else:
            warn("Guild ID: not set")
    else:
        warn(".env config: not created")

    # Check if running
    pid_file = SCRIPT_DIR / "bot.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        try:
            os.kill(int(pid), 0)
            success(f"Bot process: running (PID {pid})")
        except (OSError, ValueError):
            warn("Bot process: not running (stale pid file)")
    else:
        info("Bot process: not running")

# ── Main menu ──────────────────────────────────────────────────────

def main():
    banner()

    while True:
        print(f"""
  {BOLD}What would you like to do?{RESET}

    {CYAN}1{RESET}  Full Setup (install + configure — start here!)
    {CYAN}2{RESET}  Install Dependencies Only
    {CYAN}3{RESET}  Configure Bot Token & Server
    {CYAN}4{RESET}  Show Bot Commands & Keywords
    {CYAN}5{RESET}  Start Bot (foreground — see live output)
    {CYAN}6{RESET}  Start Bot (background)
    {CYAN}7{RESET}  Stop Background Bot
    {CYAN}8{RESET}  Check Status
    {CYAN}0{RESET}  Exit
""")
        choice = prompt("Choose an option", "1")

        actions = {
            "1": full_setup,
            "2": install_dependencies,
            "3": configure_bot,
            "4": show_commands,
            "5": test_bot,
            "6": run_bot_background,
            "7": stop_bot,
            "8": check_status,
            "0": lambda: sys.exit(0),
        }

        action = actions.get(choice)
        if action:
            action()
        else:
            warn("Invalid option — pick a number from the menu")


if __name__ == "__main__":
    main()
