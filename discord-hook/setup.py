#!/usr/bin/env python3
"""
Emma's Garden Bot — Setup Wizard
Interactive CLI to install dependencies, configure the bot, manage the systemd service,
monitor logs, and view stats.
"""

import os
import sys
import subprocess
import shutil
import json
from pathlib import Path
from datetime import datetime

def load_env_file(filepath):
    """Simple .env parser — no external dependency needed."""
    if not filepath.exists():
        return {}
    env = {}
    for line in filepath.read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"
ENV_EXAMPLE = SCRIPT_DIR / ".env.example"
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
REPO_PATH = SCRIPT_DIR.parent
SERVICE_NAME = "emma-garden-bot"
SERVICE_FILE = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")
STATS_FILE = SCRIPT_DIR / "stats.json"
LOG_FILE = SCRIPT_DIR / "bot.log"
PID_FILE = SCRIPT_DIR / "bot.pid"

# ── Pretty printing ────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"
WHITE = "\033[97m"


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
    print(f"\n{CYAN}{BOLD}{'─' * 56}")
    print(f"  {text}")
    print(f"{'─' * 56}{RESET}\n")


def success(text):
    print(f"  {GREEN}[OK]{RESET}  {text}")


def warn(text):
    print(f"  {YELLOW}[!!]{RESET}  {text}")


def error(text):
    print(f"  {RED}[ERR]{RESET} {text}")


def info(text):
    print(f"  {DIM}[..]{RESET}  {text}")


def prompt(text, default=None):
    if default:
        val = input(f"  {BOLD}{text}{RESET} [{default}]: ").strip()
        return val if val else default
    return input(f"  {BOLD}{text}{RESET}: ").strip()


def get_venv_python():
    venv_python = SCRIPT_DIR / "venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def is_service_installed():
    return SERVICE_FILE.exists()


def get_service_status():
    """Get systemd service status. Returns (active, enabled, status_text)."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True, text=True,
        )
        active = result.stdout.strip() == "active"
    except FileNotFoundError:
        return False, False, "systemctl not found"

    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", SERVICE_NAME],
            capture_output=True, text=True,
        )
        enabled = result.stdout.strip() == "enabled"
    except FileNotFoundError:
        enabled = False

    if active:
        status = f"{GREEN}active (running){RESET}"
    else:
        status = f"{RED}inactive (stopped){RESET}"

    return active, enabled, status


def get_pid_status():
    """Check if the bot is running via PID file (non-service mode)."""
    if not PID_FILE.exists():
        return None, False
    pid = PID_FILE.read_text().strip()
    try:
        os.kill(int(pid), 0)
        return pid, True
    except (OSError, ValueError):
        return pid, False

# ── Menu actions ───────────────────────────────────────────────────

def install_dependencies():
    header("Install Python Dependencies")

    python = sys.executable
    info(f"Using Python: {python}")

    venv_path = SCRIPT_DIR / "venv"
    if not venv_path.exists():
        answer = prompt("Create a virtual environment? (recommended) [y/n]", "y")
        if answer.lower() == "y":
            info("Creating virtual environment...")
            subprocess.run([python, "-m", "venv", str(venv_path)], check=True)
            success("Virtual environment created at discord-hook/venv/")

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
    header("Configure Discord Bot")

    print(f"""  {MAGENTA}Before we start, you'll need a Discord bot token.{RESET}
  If you don't have one yet, here's how:

  {BOLD}1.{RESET} Go to {CYAN}https://discord.com/developers/applications{RESET}
  {BOLD}2.{RESET} Click "New Application" — name it "Emma's Garden Bot"
  {BOLD}3.{RESET} Go to the "Bot" tab on the left
  {BOLD}4.{RESET} Click "Reset Token" and copy the token
  {BOLD}5.{RESET} Under "Privileged Gateway Intents", enable:
     - {BOLD}PRESENCE INTENT{RESET}
     - {BOLD}SERVER MEMBERS INTENT{RESET}
     - {BOLD}MESSAGE CONTENT INTENT{RESET} (required!)
  {BOLD}6.{RESET} Go to "OAuth2" > "URL Generator"
     - Scopes: {BOLD}bot{RESET}
     - Permissions: {BOLD}Send Messages, View Channels, Read Message History, Manage Channels{RESET}
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

    # Check if Claude CLI is available
    claude_path = shutil.which("claude")
    if claude_path:
        success(f"Claude CLI detected at {claude_path} — AI commands will work automatically!")
    else:
        info("Claude CLI not found — run option 16 later to set up AI commands.")

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

  {BOLD}Roles:{RESET} Head Gardener (full), Garden Helper (most), Idea Planter (ideas+status), Spectator (help only)
  {BOLD}On Success:{RESET} Bot confirms the action + shows git push status.
  {BOLD}On Failure:{RESET} Bot replies with "Something wilted... <error details>"
""")


def test_bot():
    header("Start Bot (Foreground)")

    if not ENV_FILE.exists():
        error("No .env file found — run Configure first!")
        return

    python = get_venv_python()
    info("Starting bot (press Ctrl+C to stop)...")
    print()
    try:
        subprocess.run([python, str(SCRIPT_DIR / "bot.py")])
    except KeyboardInterrupt:
        print()
        success("Bot stopped.")


def run_bot_background():
    header("Start Bot (Background)")

    if not ENV_FILE.exists():
        error("No .env file found — run Configure first!")
        return

    if is_service_installed():
        warn("Systemd service is installed — use option 10 to start the service instead.")
        answer = prompt("Start as background process anyway? [y/n]", "n")
        if answer.lower() != "y":
            return

    python = get_venv_python()
    info("Starting bot in background...")

    if PID_FILE.exists():
        old_pid = PID_FILE.read_text().strip()
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
            pass

    with open(LOG_FILE, "a") as log:
        proc = subprocess.Popen(
            [python, str(SCRIPT_DIR / "bot.py")],
            stdout=log, stderr=log,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid))
    success(f"Bot started in background (PID {proc.pid})")
    info(f"Logs: {LOG_FILE}")
    info(f"Stop with: option 7 from this menu")


def stop_bot():
    header("Stop Background Bot")

    pid_file = SCRIPT_DIR / "bot.pid"
    if not pid_file.exists():
        warn("No bot.pid file found — bot may not be running")
        return

    pid = pid_file.read_text().strip()
    try:
        os.kill(int(pid), 15)
        success(f"Sent stop signal to PID {pid}")
        pid_file.unlink()
    except (OSError, ValueError) as e:
        warn(f"Could not stop process: {e}")
        pid_file.unlink()


def configure_claude():
    header("Configure Claude AI (Local CLI)")

    print(f"""  {MAGENTA}The bot uses your local Claude Code CLI for AI commands:{RESET}
    - {GREEN}!garden ask{RESET}      — ask any gardening question
    - {GREEN}!garden diagnose{RESET} — get help with plant problems
    - {GREEN}!garden plan{RESET}     — get a personalized weekly to-do list

  {BOLD}No API key needed!{RESET} The bot relays questions through the Claude CLI
  already installed on this machine, using your existing OAuth login.
""")

    # Check if claude is available
    claude_path = shutil.which("claude")
    if claude_path:
        success(f"Claude CLI found: {claude_path}")
    else:
        error("Claude CLI not found!")
        print(f"""
  {BOLD}Install it with:{RESET}
    {CYAN}npm install -g @anthropic-ai/claude-code{RESET}

  Then log in:
    {CYAN}claude{RESET}
  (follow the OAuth prompts to authenticate)
""")
        return

    # Test it
    info("Testing Claude CLI...")
    result = subprocess.run(
        [claude_path, "-p", "--output-format", "text", "--max-turns", "1"],
        input="Say 'hello' and nothing else.",
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode == 0 and result.stdout.strip():
        success(f"Claude responded: {result.stdout.strip()[:50]}")
        print()
        success("Claude AI is ready! The bot will use it for !garden ask/diagnose/plan.")
    else:
        err = result.stderr.strip()[:200] if result.stderr else "no response"
        error(f"Claude test failed: {err}")
        print(f"""
  {BOLD}Try running:{RESET}
    {CYAN}claude -p "hello"{RESET}

  If that doesn't work, you may need to log in:
    {CYAN}claude{RESET}
  (follow the OAuth prompts)
""")

    # Optionally set a custom path
    print()
    custom = prompt("Custom Claude CLI path (press Enter to use default)", "")
    if custom:
        if ENV_FILE.exists():
            content = ENV_FILE.read_text()
            if "CLAUDE_CLI_PATH" in content:
                lines = content.split("\n")
                lines = [
                    f"CLAUDE_CLI_PATH={custom}" if l.startswith("CLAUDE_CLI_PATH") else l
                    for l in lines
                ]
                ENV_FILE.write_text("\n".join(lines))
            else:
                with open(ENV_FILE, "a") as f:
                    f.write(f"CLAUDE_CLI_PATH={custom}\n")
            success(f"Custom CLI path saved: {custom}")


def configure_oauth():
    header("Configure OAuth / Bot Invite")

    print(f"""  {MAGENTA}This generates the invite URL to add the bot to your Discord server.{RESET}

  {BOLD}To find your Application ID:{RESET}
  {BOLD}1.{RESET} Go to {CYAN}https://discord.com/developers/applications{RESET}
  {BOLD}2.{RESET} Click on your bot application
  {BOLD}3.{RESET} The Application ID is on the {BOLD}General Information{RESET} page
     (it's also called "Client ID")
""")

    # Try to load existing
    app_id = ""
    if ENV_FILE.exists():
        env = load_env_file(ENV_FILE)
        app_id = env.get("DISCORD_APP_ID", "")

    app_id = prompt("Application (Client) ID", app_id or "")
    if not app_id:
        error("Application ID is required!")
        return

    # Bot permissions:
    # Manage Channels (16) + View Channels (1024) + Send Messages (2048) +
    # Read Message History (65536) + Add Reactions (64)
    permissions = 16 | 1024 | 2048 | 65536 | 64  # = 68672

    url = f"https://discord.com/oauth2/authorize?client_id={app_id}&permissions={permissions}&scope=bot"

    print(f"""
  {GREEN}{BOLD}Your bot invite URL:{RESET}

    {CYAN}{url}{RESET}

  {BOLD}Open this URL in your browser, pick your server, and authorize.{RESET}

  Permissions included:
    - Manage Channels     {DIM}(auto-create #garden-updates & #garden-uploads){RESET}
    - View Channels
    - Send Messages
    - Read Message History
    - Add Reactions       {DIM}(react to uploads with checkmarks){RESET}
""")

    # Save app ID
    if ENV_FILE.exists():
        content = ENV_FILE.read_text()
        if "DISCORD_APP_ID" in content:
            lines = content.split("\n")
            lines = [
                f"DISCORD_APP_ID={app_id}" if l.startswith("DISCORD_APP_ID") else l
                for l in lines
            ]
            ENV_FILE.write_text("\n".join(lines))
        else:
            with open(ENV_FILE, "a") as f:
                f.write(f"DISCORD_APP_ID={app_id}\n")
        success("Application ID saved to .env")
    else:
        warn("No .env file — the URL still works, but ID won't be remembered.")


# ── Systemd service ───────────────────────────────────────────────

def install_service():
    header("Install Systemd Service (Start at Boot)")

    if os.geteuid() != 0:
        error("This requires root privileges.")
        print()
        info("Run this command instead:")
        print(f"\n    {CYAN}sudo {get_venv_python()} {SCRIPT_DIR / 'setup.py'}{RESET}\n")
        info("Then pick this option again from the menu.")
        return

    python = get_venv_python()
    user = os.getenv("SUDO_USER", os.getenv("USER", "root"))

    service_content = f"""[Unit]
Description=Emma's Garden Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={SCRIPT_DIR}
ExecStart={python} {SCRIPT_DIR / 'bot.py'}
Restart=on-failure
RestartSec=10
StandardOutput=append:{LOG_FILE}
StandardError=append:{LOG_FILE}

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={REPO_PATH} {SCRIPT_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""

    print(f"  This will create a systemd service that:")
    print(f"    - Starts the bot automatically at boot")
    print(f"    - Restarts it if it crashes (after 10s)")
    print(f"    - Runs as user: {CYAN}{user}{RESET}")
    print(f"    - Logs to: {CYAN}{LOG_FILE}{RESET}")
    print()

    answer = prompt("Install the service? [y/n]", "y")
    if answer.lower() != "y":
        return

    SERVICE_FILE.write_text(service_content)
    success(f"Service file written to {SERVICE_FILE}")

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    success("systemd reloaded")

    subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
    success(f"Service enabled (will start at boot)")

    answer = prompt("Start the service now? [y/n]", "y")
    if answer.lower() == "y":
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)
        success("Service started!")
        print()
        service_status()


def uninstall_service():
    header("Uninstall Systemd Service")

    if os.geteuid() != 0:
        error("This requires root privileges.")
        info(f"Run: sudo {get_venv_python()} {SCRIPT_DIR / 'setup.py'}")
        return

    if not is_service_installed():
        warn("Service is not installed.")
        return

    answer = prompt("Remove the systemd service? [y/n]", "n")
    if answer.lower() != "y":
        return

    subprocess.run(["systemctl", "stop", SERVICE_NAME], capture_output=True)
    subprocess.run(["systemctl", "disable", SERVICE_NAME], capture_output=True)
    SERVICE_FILE.unlink(missing_ok=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)

    success("Service stopped, disabled, and removed.")


def service_control():
    header("Service Control")

    if not is_service_installed():
        warn("Systemd service not installed. Use option 9 to install it.")
        return

    active, enabled, status_text = get_service_status()

    print(f"  Service: {BOLD}{SERVICE_NAME}{RESET}")
    print(f"  Status:  {status_text}")
    print(f"  Enabled: {'yes (starts at boot)' if enabled else 'no'}")
    print()

    print(f"    {CYAN}1{RESET}  Start service")
    print(f"    {CYAN}2{RESET}  Stop service")
    print(f"    {CYAN}3{RESET}  Restart service")
    print(f"    {CYAN}4{RESET}  Enable (start at boot)")
    print(f"    {CYAN}5{RESET}  Disable (don't start at boot)")
    print(f"    {CYAN}0{RESET}  Back to main menu")
    print()

    choice = prompt("Choose", "0")
    cmds = {
        "1": "start", "2": "stop", "3": "restart",
        "4": "enable", "5": "disable",
    }

    if choice in cmds:
        cmd = cmds[choice]
        result = subprocess.run(
            ["systemctl", cmd, SERVICE_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            success(f"Service {cmd} successful")
        else:
            error(f"Failed: {result.stderr.strip()}")
            if "Access denied" in result.stderr or "Permission denied" in result.stderr:
                info(f"Try: sudo systemctl {cmd} {SERVICE_NAME}")


# ── Monitoring & Logs ──────────────────────────────────────────────

def view_logs():
    header("Bot Logs")

    print(f"    {CYAN}1{RESET}  View last 30 lines of bot.log")
    print(f"    {CYAN}2{RESET}  View last 100 lines of bot.log")
    print(f"    {CYAN}3{RESET}  Follow logs live (Ctrl+C to stop)")
    print(f"    {CYAN}4{RESET}  View systemd journal logs")
    print(f"    {CYAN}5{RESET}  Clear bot.log")
    print(f"    {CYAN}0{RESET}  Back to main menu")
    print()

    choice = prompt("Choose", "1")

    if choice == "1":
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text().split("\n")
            for line in lines[-30:]:
                print(f"  {DIM}{line}{RESET}")
        else:
            warn("No bot.log file found yet.")

    elif choice == "2":
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text().split("\n")
            for line in lines[-100:]:
                print(f"  {DIM}{line}{RESET}")
        else:
            warn("No bot.log file found yet.")

    elif choice == "3":
        if LOG_FILE.exists():
            info("Following logs (Ctrl+C to stop)...")
            print()
            try:
                subprocess.run(["tail", "-f", str(LOG_FILE)])
            except KeyboardInterrupt:
                print()
                success("Stopped following logs.")
        elif is_service_installed():
            info("Following journal logs (Ctrl+C to stop)...")
            print()
            try:
                subprocess.run(["journalctl", "-u", SERVICE_NAME, "-f", "--no-pager"])
            except KeyboardInterrupt:
                print()
                success("Stopped following logs.")
        else:
            warn("No log file or service found.")

    elif choice == "4":
        if is_service_installed():
            result = subprocess.run(
                ["journalctl", "-u", SERVICE_NAME, "-n", "50", "--no-pager"],
                capture_output=True, text=True,
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {DIM}{line}{RESET}")
            else:
                warn("No journal entries found.")
        else:
            warn("Systemd service not installed — no journal logs available.")

    elif choice == "5":
        if LOG_FILE.exists():
            answer = prompt("Clear all logs? [y/n]", "n")
            if answer.lower() == "y":
                LOG_FILE.write_text("")
                success("Logs cleared.")
        else:
            warn("No bot.log file to clear.")


def service_status():
    header("Full Status Dashboard")

    # ── Environment ──
    print(f"  {BOLD}Environment{RESET}")
    venv_path = SCRIPT_DIR / "venv"
    if venv_path.exists():
        success("Virtual environment: installed")
    else:
        warn("Virtual environment: not created")

    if ENV_FILE.exists():
        success(".env config: exists")
    else:
        warn(".env config: not created — run Configure (option 3)")

    # ── Bot process ──
    print(f"\n  {BOLD}Bot Process{RESET}")
    pid, running = get_pid_status()
    if running:
        success(f"Background process: running (PID {pid})")
    elif pid:
        warn(f"Background process: dead (stale PID {pid})")
    else:
        info("Background process: not running")

    # ── Systemd service ──
    print(f"\n  {BOLD}Systemd Service{RESET}")
    if is_service_installed():
        active, enabled, status_text = get_service_status()
        print(f"  {GREEN}[OK]{RESET}  Installed: yes")
        print(f"  {'  ' * 1}    Status:  {status_text}")
        print(f"  {'  ' * 1}    Boot:    {'enabled' if enabled else 'disabled'}")

        # Uptime
        if active:
            result = subprocess.run(
                ["systemctl", "show", SERVICE_NAME, "--property=ActiveEnterTimestamp"],
                capture_output=True, text=True,
            )
            ts = result.stdout.strip().split("=", 1)[-1].strip()
            if ts:
                info(f"Running since: {ts}")
    else:
        info("Not installed — use option 9 to set up")

    # ── Config details ──
    print(f"\n  {BOLD}Configuration{RESET}")
    if ENV_FILE.exists():
        env = load_env_file(ENV_FILE)
        token = env.get("DISCORD_BOT_TOKEN", "")
        if token and token != "your-bot-token-here":
            success(f"Bot token: {token[:8]}...{token[-4:]}")
        else:
            warn("Bot token: not set")
        guild = env.get("GUILD_ID", "")
        if guild:
            success(f"Guild ID: {guild}")
        else:
            warn("Guild ID: not set")
        channel = env.get("CHANNEL_NAME", "garden-updates")
        success(f"Channel: #{channel}")
        push = env.get("GIT_PUSH", "true")
        success(f"Auto-push: {push}")
        repo = env.get("REPO_PATH", str(REPO_PATH))
        success(f"Repo: {repo}")
    else:
        warn("No config file found")

    # ── Log file ──
    print(f"\n  {BOLD}Logs{RESET}")
    if LOG_FILE.exists():
        size = LOG_FILE.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        success(f"bot.log: {size_str}")

        lines = LOG_FILE.read_text().strip().split("\n")
        if lines and lines[-1]:
            info(f"Last entry: {lines[-1][:80]}")
    else:
        info("No bot.log yet")

    # ── Git status ──
    print(f"\n  {BOLD}Git Repository{RESET}")
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_PATH), "log", "--oneline", "-1"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            success(f"Latest commit: {result.stdout.strip()}")

        result = subprocess.run(
            ["git", "-C", str(REPO_PATH), "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            warn(f"Uncommitted changes: {len(result.stdout.strip().split(chr(10)))} files")
        else:
            success("Working tree: clean")

        result = subprocess.run(
            ["git", "-C", str(REPO_PATH), "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            success(f"Remote: {result.stdout.strip()}")
    except FileNotFoundError:
        warn("git not found")


def generate_invite_url():
    header("Generate Bot Invite URL")

    print(f"""  {MAGENTA}This generates the OAuth2 URL to invite the bot to your server.{RESET}
  You need the Application ID from the Discord Developer Portal.
  (It's on the "General Information" page of your app.)
""")

    # Try to read from .env if we have a stored app ID
    app_id = ""
    if ENV_FILE.exists():
        env = load_env_file(ENV_FILE)
        app_id = env.get("DISCORD_APP_ID", "")

    app_id = prompt("Application (Client) ID", app_id or "")
    if not app_id:
        error("Application ID is required!")
        return

    # Bot permissions bitfield:
    # Manage Channels (16) + View Channels (1024) + Send Messages (2048) +
    # Read Message History (65536) + Add Reactions (64)
    permissions = 16 | 1024 | 2048 | 65536 | 64  # = 68672

    url = f"https://discord.com/oauth2/authorize?client_id={app_id}&permissions={permissions}&scope=bot"

    print(f"""
  {GREEN}{BOLD}Bot Invite URL:{RESET}

  {CYAN}{url}{RESET}

  {BOLD}Open this URL in your browser to add the bot to your server.{RESET}

  Permissions included:
    - Manage Channels (auto-create #garden-updates & #garden-uploads)
    - View Channels
    - Send Messages
    - Read Message History
    - Add Reactions
""")

    # Save app ID for future use
    if ENV_FILE.exists():
        content = ENV_FILE.read_text()
        if "DISCORD_APP_ID" not in content:
            with open(ENV_FILE, "a") as f:
                f.write(f"DISCORD_APP_ID={app_id}\n")
            success("Application ID saved to .env for next time")


def view_action_log():
    header("Action Log (Local Backup)")

    action_file = SCRIPT_DIR / "actions.jsonl"
    if not action_file.exists():
        info("No actions recorded yet. Use bot commands to start logging.")
        return

    import json

    lines = action_file.read_text().strip().split("\n")
    total = len(lines)

    # Count by command
    command_counts = {}
    user_counts = {}
    file_count = 0
    for line in lines:
        try:
            entry = json.loads(line)
            cmd = entry.get("command", "unknown")
            user = entry.get("user", "unknown")
            files = entry.get("files", [])
            command_counts[cmd] = command_counts.get(cmd, 0) + 1
            user_counts[user] = user_counts.get(user, 0) + 1
            file_count += len(files)
        except json.JSONDecodeError:
            pass

    print(f"  {BOLD}Total actions:{RESET} {total}")
    print(f"  {BOLD}Files saved locally:{RESET} {file_count}")

    # Check uploads dir size
    uploads_dir = SCRIPT_DIR / "uploads"
    if uploads_dir.exists():
        total_size = sum(f.stat().st_size for f in uploads_dir.rglob("*") if f.is_file())
        file_total = sum(1 for f in uploads_dir.rglob("*") if f.is_file())
        if total_size > 1024 * 1024:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        elif total_size > 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size} bytes"
        print(f"  {BOLD}Uploads folder:{RESET} {file_total} files ({size_str})")

    print(f"\n  {BOLD}By Command:{RESET}")
    for cmd, count in sorted(command_counts.items(), key=lambda x: -x[1]):
        bar = GREEN + "#" * min(count, 30) + RESET
        print(f"    {cmd:<25} {count:>4}  {bar}")

    print(f"\n  {BOLD}By User:{RESET}")
    for user, count in sorted(user_counts.items(), key=lambda x: -x[1]):
        bar = CYAN + "#" * min(count, 30) + RESET
        print(f"    {user:<25} {count:>4}  {bar}")

    print()
    print(f"    {CYAN}1{RESET}  Show last 20 actions")
    print(f"    {CYAN}2{RESET}  List saved files")
    print(f"    {CYAN}0{RESET}  Back")
    print()

    choice = prompt("Choose", "0")

    if choice == "1":
        print()
        for line in lines[-20:]:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                user = entry.get("user", "?")
                cmd = entry.get("command", "?")
                details = entry.get("details", "")[:60]
                files = entry.get("files", [])
                file_str = f" [{len(files)} file(s)]" if files else ""
                print(f"  {DIM}{ts}{RESET}  {CYAN}{user}{RESET}  {cmd}  {details}{file_str}")
            except json.JSONDecodeError:
                pass

    elif choice == "2":
        if uploads_dir.exists():
            for subdir in sorted(uploads_dir.iterdir()):
                if subdir.is_dir():
                    files_in = list(subdir.iterdir())
                    print(f"\n  {BOLD}{subdir.name}/{RESET} ({len(files_in)} files)")
                    for f in sorted(files_in)[-10:]:
                        size = f.stat().st_size
                        print(f"    {DIM}{f.name}{RESET} ({size:,} bytes)")
                    if len(files_in) > 10:
                        info(f"... and {len(files_in) - 10} more")
        else:
            info("No uploads directory yet.")


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
    print(f"  Start the bot:         {CYAN}option 5 or 6{RESET}")
    print(f"  Install as service:    {CYAN}option 9{RESET} (requires sudo)")
    print()


# ── Main menu ──────────────────────────────────────────────────────

def main():
    banner()

    while True:
        # Build a quick status line
        status_parts = []
        if is_service_installed():
            active, _, _ = get_service_status()
            if active:
                status_parts.append(f"{GREEN}service: running{RESET}")
            else:
                status_parts.append(f"{RED}service: stopped{RESET}")
        else:
            pid, running = get_pid_status()
            if running:
                status_parts.append(f"{GREEN}bot: running (PID {pid}){RESET}")
            else:
                status_parts.append(f"{DIM}bot: not running{RESET}")

        status_line = " | ".join(status_parts)

        print(f"""
  {DIM}[ {status_line} {DIM}]{RESET}

  {BOLD}Setup & Config{RESET}
    {CYAN}1{RESET}   Full Setup (install + configure — start here!)
    {CYAN}2{RESET}   Install Dependencies
    {CYAN}3{RESET}   Configure Bot Token & Server
    {CYAN}4{RESET}   Show Bot Commands & Keywords

  {BOLD}Connect{RESET}
    {CYAN}8{RESET}   Configure OAuth / Bot Invite   {DIM}(add bot to server){RESET}
    {CYAN}16{RESET}  Configure Claude AI            {DIM}(uses local CLI — no API key needed){RESET}

  {BOLD}Run{RESET}
    {CYAN}5{RESET}   Start Bot (foreground — see live output)
    {CYAN}6{RESET}   Start Bot (background)
    {CYAN}7{RESET}   Stop Background Bot

  {BOLD}Service (start at boot){RESET}
    {CYAN}9{RESET}   Install Systemd Service       {DIM}(requires sudo){RESET}
    {CYAN}10{RESET}  Service Control (start/stop/restart/enable/disable)
    {CYAN}11{RESET}  Uninstall Systemd Service      {DIM}(requires sudo){RESET}

  {BOLD}Monitor{RESET}
    {CYAN}12{RESET}  Full Status Dashboard
    {CYAN}13{RESET}  View Logs
    {CYAN}14{RESET}  Live Log Stream                {DIM}(Ctrl+C to stop){RESET}
    {CYAN}15{RESET}  Action Log & Stats             {DIM}(local backup){RESET}

    {CYAN}0{RESET}   Exit
""")
        choice = prompt("Choose an option", "12")

        actions = {
            "1": full_setup,
            "2": install_dependencies,
            "3": configure_bot,
            "4": show_commands,
            "5": test_bot,
            "6": run_bot_background,
            "7": stop_bot,
            "8": configure_oauth,
            "16": configure_claude,
            "9": install_service,
            "10": service_control,
            "11": uninstall_service,
            "12": service_status,
            "13": view_logs,
            "14": live_log_stream,
            "15": view_action_log,
            "0": lambda: sys.exit(0),
        }

        action = actions.get(choice)
        if action:
            action()
        else:
            warn("Invalid option — pick a number from the menu")


def live_log_stream():
    header("Live Log Stream")

    if is_service_installed():
        active, _, _ = get_service_status()
        if active:
            info("Streaming systemd journal (Ctrl+C to stop)...")
            print()
            try:
                subprocess.run(["journalctl", "-u", SERVICE_NAME, "-f", "--no-pager"])
            except KeyboardInterrupt:
                print()
                success("Stopped.")
                return

    if LOG_FILE.exists():
        info("Following bot.log (Ctrl+C to stop)...")
        print()
        try:
            subprocess.run(["tail", "-f", str(LOG_FILE)])
        except KeyboardInterrupt:
            print()
            success("Stopped.")
    else:
        warn("No log source available. Start the bot first.")


if __name__ == "__main__":
    main()
