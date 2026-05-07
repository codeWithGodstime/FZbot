import asyncio
import logging
import os
from collections.abc import Callable

import aiofiles
import aiohttp
from tqdm.asyncio import tqdm

from app.core.models import DownloadEvent, DownloadItem

logger = logging.getLogger(__name__)


class DownloadManager:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        concurrency: int,
        event_callback: Callable[[DownloadEvent], None] | None = None,
        pause_event: asyncio.Event | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self.session = session
        self.concurrency = max(1, concurrency)
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._event_callback = event_callback
        self._pause_event = pause_event or asyncio.Event()
        self._pause_event.set()
        self._cancel_event = cancel_event or asyncio.Event()

    async def download_all(self, downloads: list[DownloadItem], folder_name: str) -> None:
        for item in downloads:
            self._emit(DownloadEvent(name=item.name, status="queued"))
        tasks = [self._download_item(item, folder_name) for item in downloads]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _download_item(self, item: DownloadItem, folder_name: str) -> None:
        async with self._semaphore:
            if self._cancel_event.is_set():
                self._emit(DownloadEvent(name=item.name, status="cancelled", detail="Cancelled by user"))
                return
            await self._wait_if_paused(item.name)
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
            if self._cancel_event.is_set():
                self._emit(DownloadEvent(name=name, status="cancelled", detail="Cancelled by user"))
                return
            await self._wait_if_paused(name)
            self._emit(DownloadEvent(name=name, status="starting", downloaded_bytes=downloaded_size))
            async with self.session.head(url) as head_resp:
                total_size = int(head_resp.headers.get("Content-Length", 0)) + downloaded_size

            async with self.session.get(url, headers=headers) as resp:
                if resp.status not in (200, 206):
                    logger.error("Download failed for %s with status %s", name, resp.status)
                    self._emit(
                        DownloadEvent(
                            name=name,
                            status="failed",
                            downloaded_bytes=downloaded_size,
                            total_bytes=total_size,
                            detail=f"HTTP {resp.status}",
                        )
                    )
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
                        if self._cancel_event.is_set():
                            self._emit(
                                DownloadEvent(
                                    name=name,
                                    status="cancelled",
                                    downloaded_bytes=downloaded_size,
                                    total_bytes=total_size,
                                    detail="Cancelled by user",
                                )
                            )
                            progress.close()
                            return
                        await self._wait_if_paused(name, downloaded_size, total_size)
                        if not chunk:
                            continue
                        await handle.write(chunk)
                        downloaded_size += len(chunk)
                        progress.update(len(chunk))
                        self._emit(
                            DownloadEvent(
                                name=name,
                                status="downloading",
                                downloaded_bytes=downloaded_size,
                                total_bytes=total_size,
                            )
                        )
                progress.close()
                print("Download complete.\n")
                self._emit(
                    DownloadEvent(
                        name=name,
                        status="completed",
                        downloaded_bytes=downloaded_size,
                        total_bytes=total_size,
                    )
                )
        except aiohttp.ClientError as exc:
            logger.error("Client error occurred while downloading %s: %s", name, exc)
            self._emit(DownloadEvent(name=name, status="failed", detail=str(exc)))
        except asyncio.CancelledError:
            logger.info("Download task cancelled for %s", name)
            self._emit(DownloadEvent(name=name, status="cancelled", detail="Cancelled by user"))
            raise
        except Exception:
            logger.exception("An unexpected error occurred while downloading %s", name)
            self._emit(DownloadEvent(name=name, status="failed", detail="Unexpected error"))

    def _emit(self, event: DownloadEvent) -> None:
        if self._event_callback:
            self._event_callback(event)

    async def _wait_if_paused(
        self,
        name: str,
        downloaded_bytes: int = 0,
        total_bytes: int = 0,
    ) -> None:
        while not self._pause_event.is_set():
            if self._cancel_event.is_set():
                return
            self._emit(
                DownloadEvent(
                    name=name,
                    status="paused",
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes,
                    detail="Paused by user",
                )
            )
            await asyncio.sleep(0.2)
