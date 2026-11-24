import asyncio
import logging
import os
import shutil
import time
import uuid

from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import Message

import config
from gofile import Gofile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

START_TIME = time.time()
STATS = {"uploads": 0, "downloads": 0, "active": 0}
gofile = Gofile()
sem = asyncio.Semaphore(config.MAX_PARALLEL)

app = Client(
    "gofile_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workdir=".",
)


# ---------- helpers ----------
def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def human_time(seconds):
    seconds = int(seconds)
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s" if d else f"{h}h {m}m {s}s"


def bar(done, total, width=14):
    pct = done / total if total else 0
    filled = int(width * pct)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct * 100:.1f}%"


class Progress:
    """Throttled progress updater that edits one status message."""

    def __init__(self, msg, title):
        self.msg, self.title = msg, title
        self.last = 0
        self.start = time.time()

    async def __call__(self, done, total):
        now = time.time()
        if now - self.last < 4 and done != total:
            return
        self.last = now
        speed = done / max(now - self.start, 0.1)
        text = (
            f"{self.title}\n{bar(done, total)}\n"
            f"{human_size(done)} / {human_size(total)}\n"
            f"Speed: {human_size(speed)}/s"
        )
        try:
            await self.msg.edit_text(text)
        except Exception:
            pass


def allowed(message: Message):
    if not config.ALLOWED_USERS:
        return True
    return message.from_user and message.from_user.id in config.ALLOWED_USERS


def get_media(message: Message):
    for kind in ("document", "video", "audio", "voice", "animation", "video_note"):
        media = getattr(message, kind, None)
        if media:
            return media
    if message.photo:
        return message.photo
    return None


# ---------- commands ----------
@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start(_, m: Message):
    await m.reply_text(
        "👋 **Gofile Bot**\n\n"
        "• Send me any file (up to 4 GB) → I upload it to Gofile and give you "
        "a share link and a download link.\n"
        "• Send me a `gofile.io/d/...` link → I download it and send the file here.\n\n"
        "/status – bot status and uptime"
    )


@app.on_message(filters.command("status") & filters.private)
async def status(_, m: Message):
    await m.reply_text(
        "🟢 **Bot is running**\n"
        f"⏱ Uptime: `{human_time(time.time() - START_TIME)}`\n"
        f"⚙️ Active jobs: `{STATS['active']}`\n"
        f"⬆️ Uploads to Gofile: `{STATS['uploads']}`\n"
        f"⬇️ Gofile → Telegram: `{STATS['downloads']}`\n"
        f"🔑 Gofile account: `{'API key' if config.GOFILE_API_KEY else 'guest'}`"
    )


# ---------- Telegram -> Gofile ----------
@app.on_message(
    (filters.document | filters.video | filters.audio | filters.voice
     | filters.photo | filters.animation | filters.video_note)
    & filters.private
)
async def tg_to_gofile(_, m: Message):
    if not allowed(m):
        return await m.reply_text("⛔ You are not allowed to use this bot.")
    media = get_media(m)
    size = getattr(media, "file_size", 0) or 0
    if size > config.MAX_FILE_SIZE:
        return await m.reply_text(
            f"❌ File too large ({human_size(size)}). Limit: {human_size(config.MAX_FILE_SIZE)}."
        )

    status_msg = await m.reply_text("⏳ Queued...")
    job_dir = os.path.join(config.DOWNLOAD_DIR, uuid.uuid4().hex)
    os.makedirs(job_dir, exist_ok=True)
    async with sem:
        STATS["active"] += 1
        try:
            path = await m.download(
                file_name=job_dir + os.sep,
                progress=Progress(status_msg, "⬇️ Downloading from Telegram"),
            )
            loop = asyncio.get_running_loop()
            await status_msg.edit_text("⬆️ Uploading to Gofile...")
            last = {"t": 0}

            def on_up(done, total):
                if time.time() - last["t"] > 4 or done == total:
                    last["t"] = time.time()
                    asyncio.run_coroutine_threadsafe(
                        status_msg.edit_text(
                            f"⬆️ Uploading to Gofile\n{bar(done, total)}\n"
                            f"{human_size(done)} / {human_size(total)}"
                        ),
                        loop,
                    )

            res = await gofile.upload(path, on_up)
            STATS["uploads"] += 1
            text = (
                "✅ **Upload complete**\n\n"
                f"📄 `{res['name']}`\n"
                f"📦 {human_size(os.path.getsize(path))}\n\n"
                f"🔗 **Share link:** {res['share_link']}\n"
            )
            if res["direct_link"]:
                text += f"⬇️ **Download link:** {res['direct_link']}\n"
            await status_msg.edit_text(text, disable_web_page_preview=True)
        except Exception as e:
            log.exception("upload failed")
            await status_msg.edit_text(f"❌ Failed: `{e}`")
        finally:
            STATS["active"] -= 1
            shutil.rmtree(job_dir, ignore_errors=True)


# ---------- Gofile -> Telegram ----------
@app.on_message(filters.text & filters.regex(r"gofile\.io/d/") & filters.private)
async def gofile_to_tg(_, m: Message):
    if not allowed(m):
        return await m.reply_text("⛔ You are not allowed to use this bot.")
    content_id = gofile.extract_id(m.text)
    status_msg = await m.reply_text("🔎 Reading Gofile link...")
    try:
        token, files = await gofile.list_files(content_id)
    except Exception as e:
        return await status_msg.edit_text(f"❌ Could not read link: `{e}`")
    if not files:
        return await status_msg.edit_text("❌ No files found in that link.")

    for f in files:
        job_dir = os.path.join(config.DOWNLOAD_DIR, uuid.uuid4().hex)
        async with sem:
            STATS["active"] += 1
            try:
                path = await gofile.download(
                    token, f, job_dir,
                    Progress(status_msg, f"⬇️ Downloading {f['name']}"),
                )
                await status_msg.edit_text(f"⬆️ Sending {f['name']} to Telegram...")
                await m.reply_document(
                    path,
                    caption=f"`{f['name']}`",
                    progress=Progress(status_msg, f"⬆️ Sending {f['name']}"),
                )
                STATS["downloads"] += 1
            except Exception as e:
                log.exception("gofile download failed")
                await m.reply_text(f"❌ {f['name']}: `{e}`")
            finally:
                STATS["active"] -= 1
                shutil.rmtree(job_dir, ignore_errors=True)
    await status_msg.delete()


# ---------- web server (needed by Render) ----------
async def index(_):
    return web.json_response(
        {
            "status": "running",
            "uptime": human_time(time.time() - START_TIME),
            "active_jobs": STATS["active"],
            "uploads": STATS["uploads"],
            "downloads": STATS["downloads"],
        }
    )


async def health(_):
    return web.Response(text="ok")


async def main():
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    web_app = web.Application()
    web_app.router.add_get("/", index)
    web_app.router.add_get("/health", health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    log.info("Web server on port %s", config.PORT)

    await app.start()
    log.info("Bot started")
    await idle()
    await app.stop()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
