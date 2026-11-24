import io
import os
import re
import aiohttp

from config import GOFILE_API_KEY, GOFILE_WT

API = "https://api.gofile.io"
UPLOAD = "https://upload.gofile.io/uploadfile"
TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=600)


class ProgressFile(io.BufferedReader):
    """File reader that reports how many bytes were read (for upload progress)."""

    def __init__(self, path, callback=None):
        super().__init__(io.FileIO(path, "rb"), buffer_size=1024 * 1024)
        self.total = os.path.getsize(path)
        self.done = 0
        self.callback = callback

    def read(self, size=-1):
        data = super().read(size)
        self.done += len(data)
        if self.callback:
            self.callback(self.done, self.total)
        return data


class Gofile:
    def __init__(self):
        self.token = GOFILE_API_KEY or None

    async def _ensure_token(self, session):
        if self.token:
            return self.token
        async with session.post(f"{API}/accounts") as r:
            data = await r.json()
        if data.get("status") != "ok":
            raise RuntimeError(f"Could not create guest account: {data}")
        self.token = data["data"]["token"]
        return self.token

    async def upload(self, path, progress=None):
        """Upload a local file. Returns dict(share_link, direct_link, file_id, name)."""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            token = await self._ensure_token(session)
            reader = ProgressFile(path, progress)
            form = aiohttp.FormData()
            form.add_field("file", reader, filename=os.path.basename(path))
            try:
                async with session.post(
                    UPLOAD, data=form, headers={"Authorization": f"Bearer {token}"}
                ) as r:
                    res = await r.json()
            finally:
                reader.close()
            if res.get("status") != "ok":
                raise RuntimeError(f"Gofile upload failed: {res}")
            d = res["data"]
            out = {
                "name": d.get("name"),
                "file_id": d.get("id"),
                "share_link": d.get("downloadPage"),
                "direct_link": None,
            }
            # Try to resolve the direct download link of the new file.
            try:
                folder = d.get("parentFolder")
                info = await self._contents(session, folder, token)
                for child in info["children"].values():
                    if child.get("id") == d.get("id"):
                        out["direct_link"] = child.get("link")
            except Exception:
                pass
            return out

    async def _contents(self, session, content_id, token):
        async with session.get(
            f"{API}/contents/{content_id}",
            params={"wt": GOFILE_WT},
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            data = await r.json()
        if data.get("status") != "ok":
            raise RuntimeError(f"Gofile contents error: {data}")
        return data["data"]

    @staticmethod
    def extract_id(text):
        m = re.search(r"gofile\.io/d/([A-Za-z0-9]+)", text)
        return m.group(1) if m else None

    async def list_files(self, content_id):
        """Return (token, [files]) for a Gofile share link."""
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            token = await self._ensure_token(session)
            info = await self._contents(session, content_id, token)
            files = [
                c for c in info.get("children", {}).values() if c.get("type") == "file"
            ]
            return token, files

    async def download(self, token, file_info, dest_dir, progress=None):
        os.makedirs(dest_dir, exist_ok=True)
        name = file_info["name"]
        path = os.path.join(dest_dir, name)
        headers = {
            "Authorization": f"Bearer {token}",
            "Cookie": f"accountToken={token}",
        }
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(file_info["link"], headers=headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", file_info.get("size", 0)))
                done = 0
                with open(path, "wb") as f:
                    async for chunk in r.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            await progress(done, total)
        return path
