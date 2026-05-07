import logging
import asyncio
from collections.abc import Callable

import aiohttp

from app.core.config import AppConfig
from app.core.downloader import DownloadManager
from app.core.models import DownloadEvent, DownloadItem
from app.core.scraper import SeriesScraper

logger = logging.getLogger(__name__)


class DownloadOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        event_callback: Callable[[DownloadEvent], None] | None = None,
        pause_event: asyncio.Event | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self.config = config
        self.event_callback = event_callback
        self.pause_event = pause_event
        self.cancel_event = cancel_event

    async def collect_downloads(self) -> list[DownloadItem]:
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=self.config.concurrent_downloads)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if self.config.media_type == "movie":
                logger.warning("Movie downloads are not implemented yet.")
                return []

            scraper = SeriesScraper(session=session, config=self.config)
            return await scraper.collect_downloads()

    async def run(self) -> list[DownloadItem]:
        downloads = await self.collect_downloads()
        if not downloads:
            logger.info("No downloads were collected for %s.", self.config.title)
            return []

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=self.config.concurrent_downloads)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            manager = DownloadManager(session=session, concurrency=self.config.concurrent_downloads)
            manager = DownloadManager(
                session=session,
                concurrency=self.config.concurrent_downloads,
                event_callback=self.event_callback,
                pause_event=self.pause_event,
                cancel_event=self.cancel_event,
            )
            await manager.download_all(downloads, self.config.output_dir)
        return downloads
