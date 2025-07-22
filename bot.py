import asyncio
import logging
import aiohttp
import aiofiles
import argparse
import os
import re
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__file__)


class Scapper(ABC):
    @abstractmethod
    def scrape_search_page(self):
        ...

    @abstractmethod
    def scrape_seasons_link(self):
        ...

    @abstractmethod
    def scrape_episode_link(self):
        ...

    @abstractmethod
    def scrape_download_link(self):
        ...

    @abstractmethod
    def start(self):
        ...


class Downloader():

    @staticmethod
    async def download(session, url, name, folder_name):
        """
        Downloads a file from a given URL with support for resumable downloads.
        
        Args:
            session (aiohttp.ClientSession): The aiohttp session to perform HTTP requests.
            url (str): The URL of the file to download.
            name (str): The name of the file to save as.
            folder_name (str): The folder to save the downloaded file in.

        Returns:
            None
        """
        os.makedirs(folder_name, exist_ok=True)
        new_name = name.replace("?", "")
        output_path = os.path.join(folder_name, new_name)

        if os.path.exists(output_path):
            downloaded_size = os.path.getsize(output_path)
            headers = {'Range': f'bytes={downloaded_size}-'}
        else:
            downloaded_size = 0
            headers = {}

        try:
            async with session.head(url) as head_resp:
                total_size = int(head_resp.headers.get('Content-Length', 0)) + downloaded_size
            
            async with session.get(url, headers=headers) as resp:
                if resp.status in (200, 206):
                    mode = 'ab' if downloaded_size > 0 else 'wb'
                    progress = tqdm(total=total_size, initial=downloaded_size, unit='B', unit_scale=True, desc=f'Downloading {name}')

                    async with aiofiles.open(output_path, mode) as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            if chunk:
                                await f.write(chunk)
                                progress.update(len(chunk))
                    progress.close()
                    print("Download complete.\n")
        except aiohttp.ClientError as e:
            logger.error(f"Client error occurred while downloading {name}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")


class Parser():
    async def get_soup(self, session, url):
        """Fetches the page content and returns a BeautifulSoup object."""
        soup = None
        async with session.get(url) as response:
            body = await response.text()
            soup = BeautifulSoup(body, 'html.parser')
        return soup


class SeriesDownloader(Scapper, Parser):
    def __init__(self, series_name, session,  **pref):
        self.baseurl = "https://mobiletvshows.site/"
        self.series_title = series_name
        self.url = f"{self.baseurl}search.php?search={self.series_title.replace(' ', '+')}&beginsearch=Search&vsearch=&by=series="
        self.session = session
        self.settings = pref
        self.downloader = Downloader()
        self.download_links = []

    async def scrape_search_page(self):
        """Scrapes the search page to get the series link."""
        try: 
            search_page_soup = await self.get_soup(self.session, self.url)
            search_results = search_page_soup.select(".mainbox3 table span a")

            if not search_results:
                logger.info(f"No results found for search term '{self.series_title}'.")
                return

            exact_match = None
            for result in search_results:
                if result.text.strip().lower() == self.series_title.strip().lower():
                    exact_match = result
                    break

            if not exact_match:
                logger.info(f"Exact match for '{self.series_title}' not found. This is what is gotten instead {search_results}")
                return

            series_url = self.baseurl + exact_match["href"]
            logger.info("The series title %s is found: %s", self.series_title, series_url)

            return series_url

        except Exception as e:
            logger.error(f"An error occurred while scraping the search page: {e}")

    async def scrape_seasons_link(self, series_url):
        if self.settings['season']:
            soup = await self.get_soup(self.session, series_url)
            series_link = soup.select(".mainbox2 > a")[self.settings['season'] - 1]

            # single episode page
            season_url = self.baseurl + series_link["href"]
            logger.info("Scraping %s", series_link.text)

            soup = await self.get_soup(self.session, season_url)

            if self.settings['specific_episode']:

                episode_link_parent = soup.find_all(class_="mainbox")[self.settings['specific_episode'] - 1]
                logger.info("The number of episode for %s is %s", series_link.text, episode_link_parent)

                await self.scrape_episode_link(episode_link_parent)
            else:
                season_url = self.baseurl + series_link["href"]
                logger.info("Scraping %s", series_link.text)

                soup = await self.get_soup(self.session, season_url)
                episode_links_parent = soup.find_all(class_="mainbox")
                logger.info("The number of episode for %s is %s", series_link.text, len(episode_links_parent)) 

                # Gather all episode scraping concurrently for this season
                await asyncio.gather(*[self.scrape_episode_link(episode_link) for episode_link in episode_links_parent])
        else:
            soup = await self.get_soup(self.session, series_url)
            series_links = soup.select(".mainbox2 > a")

            for series_link in series_links:
                # single episode page
                season_url = self.baseurl + series_link["href"]
                logger.info("Scraping %s", series_link.text)

                soup = await self.get_soup(self.session, season_url)

                if self.settings['specific_episode']:

                    episode_link_parent = soup.find_all(class_="mainbox")[self.settings['specific_episode'] - 1]
                    logger.info("The number of episode for %s is %s", series_link.text, episode_link_parent)

                    await self.scrape_episode_link(episode_link_parent)
                else:
                    season_url = self.baseurl + series_link["href"]
                    logger.info("Scraping %s", series_link.text)

                    soup = await self.get_soup(self.session, season_url)
                    episode_links_parent = soup.find_all(class_="mainbox")
                    logger.info("The number of episode for %s is %s", series_link.text, len(episode_links_parent)) 

                    # Gather all episode scraping concurrently for this season
                    await asyncio.gather(*[self.scrape_episode_link(episode_link) for episode_link in episode_links_parent])
            
    async def scrape_episode_link(self, episode_link: BeautifulSoup):
        try:
            logger.debug("Scraping %s\n", episode_link.find('small').text)

            link = episode_link.find('a')

            if link:
                episode_url = self.baseurl + link["href"]
                logger.info("Opening episode link: %s", link.text)  # high mp4, avi, webm

                soup = await self.get_soup(self.session, episode_url)

                episode_name = episode_link.find("b").text.strip()

                # Check the type of link and format the episode name
                if "high mp4" in link.text.lower():
                    episode_name = f"{episode_name}.mp4"  # Add .mp4 extension for high mp4
                else:
                    episode_name = f"{episode_name}.{link.text.lower()[1:-1]}"  # Use link text as extension

                logger.info("Formatted episode name with extension to save with: %s", episode_name)

                # Scrape the download link
                download_url = await self.scrape_download_link(soup)
                if download_url:
                    # Store the download link and episode name
                    self.download_links.append({"link": download_url, "name": episode_name})
                    logger.info(f"Added download link for {episode_name}")
                else:
                    # Log warning if no download link is found
                    logger.warning("Download link not found for episode %s", episode_name)
        except Exception as e:
            # Log critical error for unhandled exceptions
            logger.critical(f"An error occurred while scraping episode link: {e}")

    async def scrape_download_link(self, soup: BeautifulSoup):
        download_page_link = soup.select_one("#dlink2")
        if download_page_link:
            download_url = self.baseurl + download_page_link["href"]
            soup = await self.get_soup(self.session, download_url)

            download_button = soup.select(".downloadlinks2 input")[1]
            if download_button:
                return download_button['value']
        return None

    async def start(self):
        series_url = await self.scrape_search_page()
        await self.scrape_seasons_link(series_url)

        tasks = [self.downloader.download(self.session, url.get("link"), url.get(
            "name"), self.series_title) for url in self.download_links]

        await asyncio.gather(*tasks, return_exceptions=True)

        return super().start()


class SeriesDownloaderWithoutSearch(SeriesDownloader):
    async def start(self, url):
        series_url = url
        await self.scrape_seasons_link(series_url)

        tasks = [self.downloader.download(self.session, url.get("link"), url.get(
            "name"), self.series_title) for url in self.download_links]

        await asyncio.gather(*tasks, return_exceptions=True)


async def main(*args, **kwargs):

    title = kwargs['title']
    type = kwargs['type_']
    limit_episode = kwargs['ne']
    season = kwargs['ns']
    specific_episode = kwargs['se']
    url = kwargs['url']

    settings = dict(
        title=title,
        type=type,
        limit_episode=limit_episode,
        season=season,
        specific_episode=specific_episode
    )

    timeout = aiohttp.ClientTimeout(total=0)
    max_connection = aiohttp.TCPConnector(limit=2)

    async with aiohttp.ClientSession(connector=max_connection, timeout=timeout) as session:
        if type == 'movie':
            pass
        else: 
            if url:
                instance = SeriesDownloaderWithoutSearch(title, session, **settings)
                await instance.start(url)
            else:
                scrape_instance = SeriesDownloader(title, session, **settings)
                await scrape_instance.start()


def entry():
    parser = argparse.ArgumentParser(
        description="A ClI utility program to download movies from FZmovies website"
    )

    parser.add_argument(
        'type',
        help="Movie or Series",
        choices=['movie', 'series']
    )

    parser.add_argument(
        'title',
        help="Name of movie/series you want to download"
    )

    parser.add_argument(
        '-ns', "--number_of_season",
        metavar="NS",
        type=int,
        help="Specify the season you want to download"
    )

    parser.add_argument(
        "-ne",
        "--limit_episode",
        type=int,
        default=10,
        help="Restrict the number of episodes you want to download"
    )

    parser.add_argument(
        "-se",
        "--single_episode",
        type=int,
        help="Restrict the number of episodes you want to download"
    )

    parser.add_argument(
        "-url",
        "--url",
        type=str,
        help="URl of the series you want to download"
    )

    arguments = parser.parse_args()

    asyncio.run(main(type_=arguments.type, title=arguments.title, url=arguments.url, ns=arguments.number_of_season, ne=arguments.limit_episode, se=arguments.single_episode))

entry()