import asyncio
import logging
import time
import os
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from tqdm.asyncio import trange, tqdm


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__file__)


class Downloader(ABC):
    def __init__(self, movie_title, type, number_of_seasons=1):
        self.type = type
        self.movie_title = movie_title
        self.number_of_seasons = number_of_seasons
        self.url = None
        self.download_links = []

    @abstractmethod
    def scrape_site(self):
        ...

    async def get_soup(self, session, url):
        """Fetches the page content and returns a BeautifulSoup object."""
        start_time = time.time()
        soup = None
        async with session.get(url) as response:
            body = await response.text()
            logger.debug(f"Finishing fetching {url}")
            soup = BeautifulSoup(body, 'html.parser')
            endtime = time.time()
            logger.debug(f"Scraping time: {endtime - start_time} seconds")
        return soup

    @staticmethod
    async def download(session, url, name, max_retries=3, retry_delay=1):
        """
        Downloads a file asynchronously with retries for network-related errors.
        """
        decoded_bytes_downloaded = os.path.getsize(
            name) if os.path.exists(name) else 0

        attempt = 0
        decoded_bytes_downloaded_this_session = 0

        while attempt < max_retries:
            

            try:
                async with session.get(url) as response:
                    if 'Content-Length' not in response.headers:
                        print('STOP: request headers do not contain Content-Length')
                        return

                    if ('Accept-Ranges', 'bytes') not in response.headers.items():
                        print(
                            'STOP: request headers do not contain Accept-Ranges: bytes')
                        with session.get(url) as r:
                            print(str(r.content, encoding='iso-8859-1'))

                    content_size = int(
                        response.headers.get("Content-Length", 0))

                    if decoded_bytes_downloaded >= content_size:
                        print('STOP: file already downloaded. decoded_bytes_downloaded>=r.headers[Content-Length]; {}>={}'.format(
                            decoded_bytes_downloaded, response.headers['Content-Length']))
                        return

                    # Open file in append mode if resuming
                    with open(name, "ab") as f:
                        chunk_size = 32 * 1024
                        pbar = tqdm(total=int(content_size), initial=int(
                            decoded_bytes_downloaded), unit_scale=True, desc=name)

                        while True:
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            decoded_bytes_downloaded += len(chunk)
                            pbar.update(len(chunk))

                            # Stop if we downloaded enough data
                            if content_size and decoded_bytes_downloaded >= content_size:
                                break
                    pbar.close()

                    # Check if the downloaded size matches the content length
                    if content_size and decoded_bytes_downloaded != content_size:
                        logger.warning(
                            f"Warning: Downloaded size ({decoded_bytes_downloaded}) does not match Content-Length ({content_size})."
                        )

                    logger.info(f"Download completed successfully: {name}")

# aiohttp.ClientConnectionError, aiohttp.ClientResponseError, asyncio.CancelledError
            except (asyncio.TimeoutError) as e:
                attempt += 1
                logger.warning(f"Attempt {attempt} of {
                               max_retries} failed for {url}: {e}")
                await asyncio.sleep(retry_delay)  # Wait before retrying
                if attempt == max_retries:
                    logger.error(f"Download failed after {
                                 max_retries} attempts for {url}")

            except Exception as e:
                logger.exception(f"An unexpected error occurred: {e}")
                break  # Break the loop on unexpected errors


class SeriesDownloader(Downloader):
    def __init__(self, movie_title, type='series', number_of_seasons=1, number_of_episodes=1):
        super().__init__(movie_title, type, number_of_seasons)
        self.baseurl = 'https://mobiletvshows.site/'
        self.search_term = movie_title
        self.url = f"{self.baseurl}search.php?search={
            self.search_term.replace(' ', '+')}&beginsearch=Search&vsearch=&by=series="
        self.download_links = []
        self.number_of_episodes = number_of_episodes

    async def scrape_site(self, session):
        try:
            search_page_soup = await self.get_soup(session, self.url)
            search_results = search_page_soup.select(
                ".mainbox3 table span a")  # Get all results

            if not search_results:
                logger.error(f"{self.search_term} not found. Please check the name.")
                return

            # Find the exact match
            exact_match = None
            for result in search_results:
                if result.text.strip().lower() == self.search_term.strip().lower():
                    exact_match = result
                    break

            if not exact_match:
                logger.error(f"Exact match for '{
                            self.search_term}' not found. Please check the name.")
                return

            show_url = self.baseurl + exact_match["href"]
            logger.debug("Opening exact match link: %s", show_url)

            season_links = await self.get_season_links(session, show_url)
            await asyncio.gather(*[self.scrape_season(session, season_link) for season_link in season_links])

        except Exception as e:
            logger.critical(f"An error occurred: {e}")

    async def get_season_links(self, session, show_url):
        soup = await self.get_soup(session, show_url)
        return soup.select(".mainbox2 > a")[:self.number_of_seasons]

    async def scrape_season(self, session, season_link):
        season_url = self.baseurl + season_link["href"]
        logger.debug("Fetching season link: %s", season_link.text)

        soup = await self.get_soup(session, season_url)
        episode_links_parent = soup.find_all(class_="mainbox")[
            :self.number_of_episodes]

        # Gather all episode scraping concurrently
        await asyncio.gather(*[self.scrape_episode(session, episode_link) for episode_link in episode_links_parent])
        logger.info(f"Completed downloading season: {season_link.text}")

    async def scrape_episode(self, session, episode_link):
        link = episode_link.find('a')
        episode_name = str(episode_link.find("b").text) + ".mp4" #TODO Make this configurable because some series can be in different format e.g AVI

        if link:
            episode_url = self.baseurl + link["href"]
            logger.info("Opening episode link: %s", link.text)
            soup = await self.get_soup(session, episode_url)

            download_url = await self.get_download_url(session, soup)
            if download_url:
                self.download_links.append(
                    {"link": download_url, "name": episode_name})
                logger.info(f"Added download link for {episode_name}")
            else:
                logger.warning("Download link not found for episode.")

    async def get_download_url(self, session, soup):
        download_page_link = soup.select_one("#dlink2")
        if download_page_link:
            download_url = self.baseurl + download_page_link["href"]
            soup = await self.get_soup(session, download_url)

            download_button = soup.select_one(".downloadlinks2 input")
            if download_button:
                return download_button['value']
        return None


class MovieDownloader(Downloader):
    def __init__(self, movie_title, type='series', number_of_seasons=1):
        super().__init__(movie_title, type, number_of_seasons)

    async def scrape_site(self, session):
        return super().scrape_site()
