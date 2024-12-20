import asyncio
import logging
import aiohttp
import os
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

    async def get_soup(self, session, url):
        """Fetches the page content and returns a BeautifulSoup object."""
        soup = None
        async with session.get(url) as response:
            body = await response.text()
            soup = BeautifulSoup(body, 'html.parser')
        return soup

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
        download_folder_path = os.path.join(folder_name, name)
        decoded_bytes_downloaded = os.path.getsize(download_folder_path) if os.path.exists(download_folder_path) else 0

        try:
            async with session.get(url) as response:
                # Check required headers for resumable download
                print(response.headers)
                if 'Content-Length' not in response.headers:
                    logger.error('STOP: Request headers do not contain Content-Length')
                    return

                if response.headers.get('Accept-Ranges', '').lower() != 'bytes':
                    logger.error('STOP: Request headers do not contain Accept-Ranges: bytes')
                    return

                content_size = int(response.headers["Content-Length"])

                # File already fully downloaded
                if decoded_bytes_downloaded >= content_size:
                    logger.info(f"File already downloaded: {name} ({decoded_bytes_downloaded}/{content_size} bytes)")
                    return

                # Prepare for resuming download
                headers = {}
                if decoded_bytes_downloaded > 0:
                    headers = {'Range': f'bytes={decoded_bytes_downloaded}-{content_size - 1}'}
                    logger.info(f"Resuming download: {name} from byte {decoded_bytes_downloaded}")

                # Re-send request with range header if resuming
                async with session.get(url, headers=headers) as resumed_response:
                    if resumed_response.status not in [200, 206]:
                        logger.error(f"Failed to resume download. HTTP Status: {resumed_response.status}")
                        return
                        
                    with open(download_folder_path, "ab") as f:
                        chunk_size = 16 * 1024
                        pbar = tqdm(total=content_size, initial=decoded_bytes_downloaded, unit_scale=True, desc=name)

                        while True:
                            chunk = await resumed_response.content.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            decoded_bytes_downloaded += len(chunk)
                            pbar.update(len(chunk))

                        pbar.close()

                # Validate download size
                if decoded_bytes_downloaded != content_size:
                    logger.warning(
                        f"Downloaded size ({decoded_bytes_downloaded}) does not match Content-Length ({content_size})."
                    )
                else:
                    logger.info(f"Download completed successfully: {name}")

        except aiohttp.ClientError as e:
            logger.error(f"Client error occurred while downloading {name}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")



class Series(Scapper):
    def __init__(self, title, seasons):
        """
        Initializes an instance of the class for managing TV series information.

        Args:
            title (str): The title of the TV series.
            seasons (int): The number of seasons in the TV series.
            episodes (int): The total number of episodes in the TV series. #TODO: add later

        Attributes:
            baseurl (str): The base URL of the TV shows website.
            series_title (str): The title of the TV series as provided.
            url (str): The dynamically generated search URL for the series.
            seasons (int): The number of seasons in the series.
            episodes (int): The number of episodes in the series.
        """
        self.baseurl = "https://mobiletvshows.site/"
        self.series_title = title
        self.url = f"{self.baseurl}search.php?search={self.series_title.replace(' ', '+')}&beginsearch=Search&vsearch=&by=series="
        self.seasons = seasons
        self.downloader = Downloader()
        self.download_links = []
        # self.episodes = episodes

        # create a folder for the series if it doesn't exist
        folder_path = os.path.join("./", self.series_title)
    
        # Check if the folder exists, if not, create it
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    async def scrape_download_link(self, session: aiohttp.ClientSession, soup: BeautifulSoup):
        download_page_link = soup.select_one("#dlink2")
        if download_page_link:
            download_url = self.baseurl + download_page_link["href"]
            soup = await self.get_soup(session, download_url)

            download_button = soup.select_one(".downloadlinks2 input")
            if download_button:
                return download_button['value']
        return None

    async def scrape_search_page(self, session: aiohttp.ClientSession):
        """
        Scrapes the search results page to find the TV series, extract its link, 
        and scrape details about its seasons.

        Args:
            session (aiohttp.ClientSession): An active HTTP session for making asynchronous requests.

        Workflow:
            1. Retrieve the search results page and parse its content.
            2. Find all search result links related to the series.
            3. Identify the exact match for the given search term.
            4. Navigate to the series page and retrieve season links.
            5. Scrape information for each season asynchronously.

        Raises:
            Exception: Captures and logs unexpected errors during the scraping process.
        """
        try:
            # Fetch and parse the search results page
            search_page_soup = await self.get_soup(session, self.url)
            search_results = search_page_soup.select(".mainbox3 table span a")  # Get all results

            if not search_results:
                logger.info(f"No results found for search term '{self.series_title}'.")
                return

            # Find the exact match for the search term
            exact_match = None
            for result in search_results:
                if result.text.strip().lower() == self.series_title.strip().lower():
                    exact_match = result
                    break

            if not exact_match:
                logger.info(f"Exact match for '{self.series_title}' not found. This is what is gotten instead {search_results}")
                return

            # Construct the series URL and log it
            series_url = self.baseurl + exact_match["href"]
            logger.info("The series title %s is found: %s", self.series_title, series_url)

            # Retrieve all season links
            season_links = await self.scrape_seasons_link(session, series_url) #e.g s1, s2, ... s7

            # Scrape each season asynchronously
            await asyncio.gather(
                *[self.scrape_seasons_link(session, season_link) for season_link in season_links]
            )

        except aiohttp.ClientError as client_error:
            logger.critical(f"Network error occurred: {client_error}")
        except AttributeError as attr_error:
            logger.critical(f"Attribute error occurred: {attr_error}")
        except asyncio.TimeoutError:
            logger.critical("Request timed out while scraping.")
        except Exception as e:
            logger.critical(f"An unexpected error occurred: {e}")
    
    async def scrape_seasons_link(self, session: aiohttp.ClientSession, series_url: str):
        """
            Fetches and extracts season links from the series page.

            Args:
                session (aiohttp.ClientSession): An active HTTP session for making asynchronous requests.
                series_url (str): The URL of the TV series page containing season links.
        """
        
        soup = await self.get_soup(session, series_url)
        series_links = soup.select(".mainbox2 > a")

        # iterate through each series link and go scrape episode link
        for season in series_links:
            season_url = self.baseurl + season["href"]
            logger.info("Scraping %s", season.text)

            soup = await self.get_soup(session, season_url)
            episode_links_parent = soup.find_all(class_="mainbox")
            logger.info("The number of episode for %s is %s", season.text, len(episode_links_parent)) 

            # Gather all episode scraping concurrently for this season
            await asyncio.gather(*[await self.scrape_episode_link(session, episode_link) for episode_link in episode_links_parent])

    async def scrape_episode_link(self, session: aiohttp.ClientSession, episode_link: BeautifulSoup) -> None:
        """
        Scrapes the details and download link for an episode.

        This method extracts the episode name, formats it based on the type of link (e.g., "high mp4"),
        and retrieves the download URL for the episode.

        Args:
            session (aiohttp.ClientSession): The HTTP session used for making asynchronous requests.
            episode_link (BeautifulSoup): A BeautifulSoup object containing the HTML for the episode link.

        Returns:
            None

        Behavior:
            - Extracts the episode link and navigates to the episode page.
            - Formats the episode name based on the type of link (e.g., appends `.mp4` for "high mp4").
            - Retrieves the download URL from the episode page.
            - Stores the formatted episode name and download URL in `self.download_links`.

        Raises:
            Exception: Any unhandled errors encountered during scraping are propagated for debugging or logging upstream.

        Example:
            Given an `episode_link` containing "high mp4":
            - Extracts the name and appends `.mp4`.
            - Retrieves the corresponding download link and stores it in `self.download_links`.
        """
        try:
            # Log the episode being scraped
            logger.debug("Scraping %s\n", episode_link.find('small').text)

            # Extract the episode link
            link = episode_link.find('a')

            if link:
                episode_url = self.baseurl + link["href"]
                logger.info("Opening episode link: %s", link.text)  # high mp4, avi, webm

                # Navigate to the episode page
                soup = await self.get_soup(session, episode_url)

                # Get the base episode name
                episode_name = episode_link.find("b").text.strip()

                # Check the type of link and format the episode name
                if "high mp4" in link.text.lower():
                    episode_name = f"{episode_name}.mp4"  # Add .mp4 extension for high mp4
                else:
                    episode_name = f"{episode_name}.{link.text.lower()[1:-1]}"  # Use link text as extension

                logger.info("Formatted episode name with extension to save with: %s", episode_name)

                # Scrape the download link
                download_url = await self.scrape_download_link(session, soup)
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

class MovieDownloader(Scapper):
    def __init__(self, movie_title, type='series', number_of_seasons=1):
        super().__init__(movie_title, type, number_of_seasons)

    async def scrape_site(self, session):
        return super().scrape_site()


if __name__ == "__main__":
    async def main():
        
        timeout = aiohttp.ClientTimeout(total=0)
        max_connection = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(timeout=timeout, connector=max_connection) as session:
            s = Series("Dexter", 6)
            await s.scrape_search_page(session)

            tasks = [s.downloader.download(session, url.get("link"), url.get(
            "name"), s.series_title) for url in s.download_links]
        
            await asyncio.gather(*tasks, return_exceptions=True)
    
    asyncio.run(main())