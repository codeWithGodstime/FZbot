import logging

import aiohttp

from app.core.config import AppConfig
from app.core.downloader import DownloadManager
from app.core.scraper import SeriesScraper

logger = logging.getLogger(__name__)


class DownloadOrchestrator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=self.config.concurrent_downloads)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if self.config.media_type == "movie":
                logger.warning("Movie downloads are not implemented yet.")
                return

            scraper = SeriesScraper(session=session, config=self.config)
            downloads = await scraper.collect_downloads()
            if not downloads:
                logger.info("No downloads were collected for %s.", self.config.title)
                return

            manager = DownloadManager(session=session, concurrency=self.config.concurrent_downloads)
            await manager.download_all(downloads, self.config.output_dir)
