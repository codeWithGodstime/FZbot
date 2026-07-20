import asyncio
import logging
from dataclasses import replace
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

from fzbot.core.config import AppConfig
from fzbot.core.models import DownloadItem

logger = logging.getLogger(__name__)


class Parser:
    async def get_soup(self, session: aiohttp.ClientSession, url: str) -> BeautifulSoup:
        async with session.get(url) as response:
            body = await response.text()
        return BeautifulSoup(body, "html.parser")

    async def scrape_download_link(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        soup: BeautifulSoup,
        button_index: int,
    ) -> str | None:
        download_page_link = soup.select_one("#dlink2")
        if not download_page_link:
            return None

        download_url = base_url + download_page_link["href"]
        download_soup = await self.get_soup(session, download_url)
        download_buttons = download_soup.select(".downloadlinks2 input")
        if not download_buttons:
            return None
        if button_index < len(download_buttons):
            return download_buttons[button_index]["value"]
        return download_buttons[0]["value"]

    @staticmethod
    def _build_file_name(base_name: str, link_text: str) -> str:
        normalized = link_text.lower().strip()
        if "high mp4" in normalized:
            extension = "mp4"
        else:
            extension = normalized[1:-1]
        return f"{base_name}.{extension}"

    async def scrape_quality_link(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        quality_link: BeautifulSoup,
        button_index: int,
        subdir: str | None = None,
    ) -> DownloadItem | None:
        try:
            label = quality_link.find("small")
            if label:
                logger.debug("Scraping %s", label.text)

            link = quality_link.find("a")
            if not link:
                return None

            page_url = base_url + link["href"]
            logger.info("Opening quality link: %s", link.text)

            soup = await self.get_soup(session, page_url)
            title_node = quality_link.find("b")
            if not title_node:
                logger.warning("Title not found for %s", page_url)
                return None

            file_name = self._build_file_name(title_node.text.strip(), link.text)
            download_url = await self.scrape_download_link(session, base_url, soup, button_index)
            if not download_url:
                logger.warning("Download link not found for %s", file_name)
                return None

            logger.info("Added download link for %s", file_name)
            return DownloadItem(name=file_name, url=download_url, subdir=subdir)
        except Exception:
            logger.exception("An error occurred while scraping quality link")
            return None


class SeriesScraper(Parser):
    BUTTON_INDEX = 1

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

            results = await asyncio.gather(
                *[
                    self.scrape_quality_link(
                        self.session,
                        self.base_url,
                        episode_link,
                        self.BUTTON_INDEX,
                    )
                    for episode_link in episode_links_parent
                ]
            )
            for item in results:
                if item:
                    self.download_links.append(item)


class MovieScraper(Parser):
    BUTTON_INDEX = 0

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: AppConfig,
        *,
        movie_title: str | None = None,
    ) -> None:
        self.base_url = "https://fzmovies.net/"
        self.session = session
        self.movie_title = movie_title or config.title
        self.config = replace(config, title=self.movie_title)
        self.search_url = (
            f"{self.base_url}csearch.php?searchname={quote_plus(self.movie_title)}"
        )

    async def collect_downloads(self) -> list[DownloadItem]:
        use_direct_url = self.config.url if len(self.config.movie_titles) <= 1 else None
        movie_url = use_direct_url or await self.scrape_search_page()
        if not movie_url:
            return []

        quality_link = await self._resolve_quality_link(movie_url)
        if not quality_link:
            logger.warning("No quality link found for movie '%s'.", self.movie_title)
            return []

        item = await self.scrape_quality_link(
            self.session,
            self.base_url,
            quality_link,
            self.BUTTON_INDEX,
            subdir=self.movie_title,
        )
        return [item] if item else []

    async def scrape_search_page(self) -> str | None:
        try:
            search_page_soup = await self.get_soup(self.session, self.search_url)
            search_results = search_page_soup.select(".mainbox3 table span a")

            if not search_results:
                logger.info("No results found for search term '%s'.", self.movie_title)
                return None

            exact_match = next(
                (
                    result
                    for result in search_results
                    if result.text.strip().lower() == self.movie_title.strip().lower()
                ),
                None,
            )

            if not exact_match:
                logger.info("Exact match for '%s' not found.", self.movie_title)
                return None

            movie_url = self.base_url + exact_match["href"]
            logger.info("The movie title %s is found: %s", self.movie_title, movie_url)
            return movie_url
        except Exception:
            logger.exception("An error occurred while scraping the search page")
            return None

    async def _resolve_quality_link(self, movie_url: str) -> BeautifulSoup | None:
        soup = await self.get_soup(self.session, movie_url)
        mainboxes = soup.find_all(class_="mainbox")
        if mainboxes:
            return mainboxes[0]

        part_links = soup.select(".mainbox2 > a")
        if not part_links:
            return None

        part_url = self.base_url + part_links[0]["href"]
        logger.info("Following movie part link: %s", part_links[0].text)
        part_soup = await self.get_soup(self.session, part_url)
        mainboxes = part_soup.find_all(class_="mainbox")
        return mainboxes[0] if mainboxes else None
