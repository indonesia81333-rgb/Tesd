# Telegram ⇄ Gofile Bot

A Telegram bot that uploads files you send it to Gofile and returns a share link
and a download link. It can also take a Gofile link and send the file back to you in Telegram.

## Features
- Telegram → Gofile upload with live progress, share link + direct download link
- Gofile link → Telegram download/send
- Large files via MTProto (Kurigram/Pyrogram), not the 20 MB Bot API limit
- Gofile API key support (guest account if empty)
- `/status` command with uptime and job counters
- Built-in web server (`/`, `/health`) for Render
- Dockerfile + `render.yaml`

## Setup
1. Get `API_ID` and `API_HASH` from https://my.telegram.org
2. Create a bot with @BotFather and copy the `BOT_TOKEN`
3. Get your Gofile API key from your Gofile profile page (optional)
4. Copy `.env.example` to `.env`, fill it in, then:

```bash
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)
python bot.py
```

## Deploy on Render
1. Push this folder to a GitHub repo.
2. On Render: New → Blueprint (uses `render.yaml`), or New → Web Service → Docker.
3. Add the environment variables: `API_ID`, `API_HASH`, `BOT_TOKEN`, `GOFILE_API_KEY`.
4. Deploy. Open the service URL to see status and uptime as JSON.

## Important limits
- **Telegram file size:** normal accounts can send up to 2 GB per file; 4 GB only when the
  sender has Telegram Premium. Gofile → Telegram sending is capped at 2 GB.
- **Render disk/RAM:** files are staged on disk temporarily. The free plan has small, ephemeral
  disk and little RAM, so very large files may fail there. Use a paid plan or a VPS for 4 GB files.
- **Render free sleep:** free web services sleep after inactivity. Ping `/health` every 5 minutes
  with a service like UptimeRobot to keep the bot awake.
- **Gofile website token:** Gofile's content API needs a `wt` token that they occasionally change.
  If Gofile → Telegram stops working, update `GOFILE_WT`.
- Set `ALLOWED_USERS` to restrict the bot to specific Telegram user IDs.
