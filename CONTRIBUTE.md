---
layout: default
title: Contribute
permalink: /CONTRIBUTE
---

# Contribute to Emma's Garden

**Want to help Emma's balcony bloom? Here's how to get involved!**

---

## Join the Discord

The garden has its own Discord server where you can chat, share ideas, and even push updates directly to the site using bot commands.

### How to Join

1. **Get an invite link** — ask Emma or Michael for the Discord server invite
2. **Join the server** and say hi!
3. **Head to `#garden-updates`** — this is where the magic happens

Once you're in, a server admin will assign you a role based on how you'd like to help.

---

## User Roles

Not everyone should be able to change everything — so we use roles to keep things tidy and prevent accidental chaos.

| Role | What You Can Do | Who Gets It |
|------|----------------|-------------|
| **Head Gardener** | Full access — all bot commands, can update any part of the site | Emma |
| **Garden Helper** | Can add log entries, report blooms, add photos, and check status | Trusted friends and family |
| **Idea Planter** | Can submit ideas and check status — great for visitors with suggestions | Anyone who joins |
| **Spectator** | Can read `#garden-updates` but not use bot commands | Lurkers welcome! |

### Role Permissions Breakdown

| Command | Head Gardener | Garden Helper | Idea Planter | Spectator |
|---------|:---:|:---:|:---:|:---:|
| `!garden log` | Yes | Yes | - | - |
| `!garden bloom` | Yes | Yes | - | - |
| `!garden photo` | Yes | Yes | - | - |
| `!garden idea` | Yes | Yes | Yes | - |
| `!garden milestone` | Yes | - | - | - |
| `!garden status` | Yes | Yes | Yes | - |
| `!garden help` | Yes | Yes | Yes | Yes |

**Head Gardener** is the only role that can add milestones — those are big-deal achievements and should be intentional.

**Garden Helper** can do most day-to-day updates — logging progress, snapping photos, recording blooms.

**Idea Planter** is the low-barrier entry role — perfect for friends who want to suggest "you should grow sunflowers!" without accidentally editing the site.

---

## Bot Commands Quick Reference

Type these in the `#garden-updates` channel:

### Adding Updates

```
!garden log Sprouts appeared in cells 3 and 7 today!
```
Adds a timestamped entry to the Progress Report.

### Recording Blooms

```
!garden bloom First cosmos flower opened — bright pink!
```
Adds to both the session log AND the milestones table. This is for celebrations!

### Adding Photos

```
!garden photo https://i.imgur.com/example.jpg The first zinnia bloom
```
Adds a row to the Photo Log with the image and your caption.

### Submitting Ideas

```
!garden idea Try growing strawberries in a hanging basket next year
```
Adds your idea to the Future Ideas page.

### Adding Milestones

```
!garden milestone All seedlings transplanted to the balcony
```
Adds a completed milestone to the tracker. **Head Gardener only.**

### Checking Status

```
!garden status
```
Shows what's pending, in-progress, and upcoming.

---

## What Happens When You Send a Command

1. You type a command in `#garden-updates`
2. The bot edits the right markdown file in the project
3. Changes get committed and pushed to GitHub
4. GitHub Pages rebuilds the site (takes ~30 seconds)
5. The bot confirms with a success message

**On success**, you'll see something like:
> Logged! Your garden story grows...
> *Changes pushed — site will update shortly!*

**On failure**, you'll see:
> Something wilted... (error details)

If something goes wrong, let Emma or Michael know — it's usually a config or permissions issue, not your fault!

---

## Other Ways to Contribute

Not into Discord? You can still help!

- **Send Emma a text** with your garden idea — she'll add it via Discord
- **Open a GitHub issue** on the [project repo](https://github.com/rompasaurus/emmas-gardening-project) if you're code-savvy
- **Send a photo** of your own garden for inspiration — we might add a "Friends' Gardens" page someday!
- **Gift a plant** — Emma's balcony has room for more pots (there's always room for more pots)

---

## Setting Up the Bot (For Admins)

If you're helping run the server, the bot setup lives in the `discord-hook/` folder of the project.

```bash
cd discord-hook
python setup.py
```

The setup wizard walks you through everything: installing dependencies, configuring the bot token, and getting it running. See the [discord-hook/](https://github.com/rompasaurus/emmas-gardening-project/tree/main/discord-hook) folder for details.

### Creating Discord Roles

In your Discord server:

1. Go to **Server Settings > Roles**
2. Create these roles (names must match exactly):
   - `Head Gardener`
   - `Garden Helper`
   - `Idea Planter`
   - `Spectator`
3. Assign roles to members as they join
4. The bot checks roles automatically — no extra config needed

---

*The garden grows better with friends!*
