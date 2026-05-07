import asyncio
import logging
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

from app.core.config import AppConfig
from app.core.models import DownloadItem

logger = logging.getLogger(__name__)


class Parser:
    async def get_soup(self, session: aiohttp.ClientSession, url: str) -> BeautifulSoup:
        async with session.get(url) as response:
            body = await response.text()
        return BeautifulSoup(body, "html.parser")


class SeriesScraper(Parser):
    def __init__(self, session: aiohttp.ClientSession, config: AppConfig) -> None:
        self.base_url = "https://mobiletvshows.site/"
        self.session = session
        self.config = config
        self.search_url = (
            f"{self.base_url}search.php?search={quote_plus(config.title)}"
            "&beginsearch=Search&vsearch=&by=series="
        )
        self.download_links: list[DownloadItem] = []

    async def collect_downloads(self) -> list[DownloadItem]:
        series_url = self.config.url or await self.scrape_search_page()
        if not series_url:
            return []

        await self.scrape_seasons_link(series_url)

        limit = self.config.max_downloads
        if limit and limit > 0:
            return self.download_links[:limit]
        return self.download_links

    async def scrape_search_page(self) -> str | None:
        try:
            search_page_soup = await self.get_soup(self.session, self.search_url)
            search_results = search_page_soup.select(".mainbox3 table span a")

            if not search_results:
                logger.info("No results found for search term '%s'.", self.config.title)
                return None

            exact_match = next(
                (
                    result
                    for result in search_results
                    if result.text.strip().lower() == self.config.title.strip().lower()
                ),
                None,
            )

            if not exact_match:
                logger.info("Exact match for '%s' not found.", self.config.title)
                return None

            series_url = self.base_url + exact_match["href"]
            logger.info("The series title %s is found: %s", self.config.title, series_url)
            return series_url
        except Exception:
            logger.exception("An error occurred while scraping the search page")
            return None

    async def scrape_seasons_link(self, series_url: str) -> None:
        soup = await self.get_soup(self.session, series_url)
        series_links = soup.select(".mainbox2 > a")

        if self.config.season:
            try:
                series_links = [series_links[self.config.season - 1]]
            except IndexError:
                logger.error("Season %s was not found.", self.config.season)
                return

        for series_link in series_links:
            season_url = self.base_url + series_link["href"]
            logger.info("Scraping %s", series_link.text)

            season_soup = await self.get_soup(self.session, season_url)
            episode_links_parent = season_soup.find_all(class_="mainbox")

            if self.config.specific_episode:
                try:
                    episode_links_parent = [episode_links_parent[self.config.specific_episode - 1]]
                except IndexError:
                    logger.error("Episode %s was not found in %s.", self.config.specific_episode, series_link.text)
                    continue
            else:
                logger.info("The number of episode for %s is %s", series_link.text, len(episode_links_parent))

            await asyncio.gather(
                *[self.scrape_episode_link(episode_link) for episode_link in episode_links_parent]
            )

    async def scrape_episode_link(self, episode_link: BeautifulSoup) -> None:
        try:
            label = episode_link.find("small")
            if label:
                logger.debug("Scraping %s", label.text)

            link = episode_link.find("a")
            if not link:
                return

            episode_url = self.base_url + link["href"]
            logger.info("Opening episode link: %s", link.text)

            soup = await self.get_soup(self.session, episode_url)
            title_node = episode_link.find("b")
            if not title_node:
                logger.warning("Episode title not found for %s", episode_url)
                return

            episode_name = self._build_episode_name(title_node.text.strip(), link.text)
            download_url = await self.scrape_download_link(soup)
            if not download_url:
                logger.warning("Download link not found for episode %s", episode_name)
                return

            self.download_links.append(DownloadItem(name=episode_name, url=download_url))
            logger.info("Added download link for %s", episode_name)
        except Exception:
            logger.exception("An error occurred while scraping episode link")

    async def scrape_download_link(self, soup: BeautifulSoup) -> str | None:
        download_page_link = soup.select_one("#dlink2")
        if not download_page_link:
            return None

        download_url = self.base_url + download_page_link["href"]
        download_soup = await self.get_soup(self.session, download_url)
        download_buttons = download_soup.select(".downloadlinks2 input")
        if len(download_buttons) > 1:
            return download_buttons[1]["value"]
        return None

    @staticmethod
    def _build_episode_name(base_name: str, link_text: str) -> str:
        normalized = link_text.lower().strip()
        if "high mp4" in normalized:
            extension = "mp4"
        else:
            extension = normalized[1:-1]
        return f"{base_name}.{extension}"
