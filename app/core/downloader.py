import asyncio
import logging
import os

import aiofiles
import aiohttp
from tqdm.asyncio import tqdm

from app.core.models import DownloadItem

logger = logging.getLogger(__name__)


class DownloadManager:
    def __init__(self, session: aiohttp.ClientSession, concurrency: int) -> None:
        self.session = session
        self.concurrency = max(1, concurrency)
        self._semaphore = asyncio.Semaphore(self.concurrency)

    async def download_all(self, downloads: list[DownloadItem], folder_name: str) -> None:
        tasks = [self._download_item(item, folder_name) for item in downloads]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _download_item(self, item: DownloadItem, folder_name: str) -> None:
        async with self._semaphore:
            await self.download(item.url, item.name, folder_name)

    async def download(self, url: str, name: str, folder_name: str) -> None:
        os.makedirs(folder_name, exist_ok=True)
        output_path = os.path.join(folder_name, name.replace("?", ""))

        if os.path.exists(output_path):
            downloaded_size = os.path.getsize(output_path)
            headers = {"Range": f"bytes={downloaded_size}-"}
        else:
            downloaded_size = 0
            headers = {}

        try:
            async with self.session.head(url) as head_resp:
                total_size = int(head_resp.headers.get("Content-Length", 0)) + downloaded_size

            async with self.session.get(url, headers=headers) as resp:
                if resp.status not in (200, 206):
                    logger.error("Download failed for %s with status %s", name, resp.status)
                    return

                mode = "ab" if downloaded_size > 0 else "wb"
                progress = tqdm(
                    total=total_size,
                    initial=downloaded_size,
                    unit="B",
                    unit_scale=True,
                    desc=f"Downloading {name}",
                )
                async with aiofiles.open(output_path, mode) as handle:
                    async for chunk in resp.content.iter_chunked(8192):
                        if not chunk:
                            continue
                        await handle.write(chunk)
                        progress.update(len(chunk))
                progress.close()
                print("Download complete.\n")
        except aiohttp.ClientError as exc:
            logger.error("Client error occurred while downloading %s: %s", name, exc)
        except Exception:
            logger.exception("An unexpected error occurred while downloading %s", name)
