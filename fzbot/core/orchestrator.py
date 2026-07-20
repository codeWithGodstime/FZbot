import logging
import asyncio
from collections.abc import Callable

import aiohttp

from fzbot.core.config import AppConfig
from fzbot.core.downloader import DownloadManager
from fzbot.core.models import DownloadEvent, DownloadItem
from fzbot.core.scraper import MovieScraper, SeriesScraper

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
                return await self._collect_movie_downloads(session)

            scraper = SeriesScraper(session=session, config=self.config)
            return await scraper.collect_downloads()

    async def _collect_movie_downloads(self, session: aiohttp.ClientSession) -> list[DownloadItem]:
        titles = self.config.movie_titles
        if not titles:
            logger.warning("No movie titles provided.")
            return []

        results = await asyncio.gather(
            *[
                MovieScraper(session=session, config=self.config, movie_title=title).collect_downloads()
                for title in titles
            ]
        )

        downloads: list[DownloadItem] = []
        for title, items in zip(titles, results, strict=True):
            if not items:
                logger.warning("No download link collected for movie '%s'.", title)
            downloads.extend(items)

        limit = self.config.max_downloads
        if limit and limit > 0:
            return downloads[:limit]
        return downloads

    async def run(self) -> list[DownloadItem]:
        downloads = await self.collect_downloads()
        if not downloads:
            logger.info("No downloads were collected for %s.", self.config.title)
            return []

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=self.config.concurrent_downloads)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            manager = DownloadManager(
                session=session,
                concurrency=self.config.concurrent_downloads,
                event_callback=self.event_callback,
                pause_event=self.pause_event,
                cancel_event=self.cancel_event,
            )
            await manager.download_all(downloads, self.config.output_dir)
        return downloads
