import logging
import time
import os
import asyncio
import aiohttp
import argparse
from abc import abstractmethod, ABC
from bs4 import BeautifulSoup
from tqdm.asyncio import trange, tqdm

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
    '-ns', "--number_of_seasons",
    metavar="NS",
    type=int,
    default=1,
    help="Number of movie/series you want to download" 
)

arguments = parser.parse_args()
print(arguments)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__file__)


class Downloader(ABC):
    def __init__(self, movie_title, type, number_of_seasons=1):
        self.type = type
        self.movie_title = movie_title
        # self.number_of_episodes = number_of_episodes
        self.number_of_seasons = number_of_seasons
        self.url = None
        self.download_links = []

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

    @abstractmethod
    def scrape_site(self):
        ...

    @staticmethod
    async def download(session, url, name):

        try:
            # await asyncio.sleep(2)
            # print(f"Downloading {name} {url} ")
            # # if file exist
            # decoded_bytes_downloaded_this_session = 0

            # if os.path.exists(name):
            #     decoded_bytes_downloaded = os.path.getsize(name)
            # else:
            #     decoded_bytes_downloaded = 0
                
            async with session.get(url) as response:
                content_size = int(response.headers.get("Content-Length", 0))
                print("file size", content_size)
                with open(name, "wb") as f:
                    chunk_size = 4096
                    pbar = tqdm(total=int(content_size/chunk_size))
                    async for data in (response.content.iter_chunked(chunk_size)):
                        if data:
                            pbar.update()
                        f.write(data)
                
        except aiohttp.ClientConnectionError as c:
            logger.critical(f"Connection error {c}") 
        except aiohttp.ClientResponseError as e:
            logger.error(f"Invalid response {e}")
        


class SeriesDownloader(Downloader):
    def __init__(self, movie_title, type='series', number_of_seasons=1):
        super().__init__(movie_title, type, number_of_seasons)
        self.baseurl = 'https://mobiletvshows.site/'
        self.search_term = movie_title
        self.url =  f"{self.baseurl}search.php?search={self.search_term.replace(' ', '+')}&beginsearch=Search&vsearch=&by=series="
        self.download_links = []
        
    async def scrape_site(self, session):
        try:
            # search term
            search_page_soup = await self.get_soup(session, self.url)
            # Step 2: Locate the first search result link
            search_result = search_page_soup.select_one(".mainbox3 table span a")
            if not search_result:
                logger.error(f"{self.search_term} is not found, are you sure you got the name right?")
            else:
                show_url = self.baseurl + search_result["href"]
                logger.debug("Opening first search result link: %s", show_url)
                
                # Step 3: Get all season links
                soup = await self.get_soup(session, show_url)
                season_links = soup.select(".mainbox2 > a")[:self.number_of_seasons] 

                for season_link in season_links:
                    season_download_links = [] # this will store the download links for current season
                    season_url = self.baseurl + season_link["href"]
                    logger.debug("Fetching season link: %s", season_link.text)
                    soup = await self.get_soup(session, season_url)

                    # Step 4: Get all episode links for the current season
                    episode_links_parent = soup.find_all(class_="mainbox") 
                    # print("Episode links = ", episode_links_parent)
                    for episode_link in episode_links_parent:
                        link = episode_link.find('a') # get the first link beacuse if is two mp4 or webm
                        episode_name = str(episode_link.find("b").text)
                        logger.info(f"Fetching link {link}, episode name: {episode_name}")
                        episode_url = self.baseurl + link["href"]
                        logger.info("Opening episode link: %s", link.text)
                        soup = await self.get_soup(session, episode_url)

                        # Step 5: Go to the download page
                        download_page_link = soup.select_one("#dlink2")  # Replace with actual ID if different
                        if download_page_link:
                            download_url = self.baseurl + download_page_link["href"]
                            logger.info("Navigated to download page: %s", download_url)
                            soup = await self.get_soup(session, download_url)

                            # Step 6: Click the final download button
                            download_button = soup.select_one(".downloadlinks2 input")  # Replace with actual ID if different
                            if download_button:
                                final_download_url = download_button['value']
                                logger.info("Final download URL: %s for episode %s season : %s", final_download_url, episode_name, season_link.text)
                                episode_name = episode_name + ".mp4"

                                # season_download_links.append({
                                #     "link": final_download_url, 
                                #     "name": episode_name
                                # })
                                self.download_links.append({
                                    "link": final_download_url, 
                                    "name": episode_name
                                })
                                logger.info(f"Added download link for {episode_name}")
                            else:
                                logger.warning("Download button not found on the download page.")
                        else:
                            logger.warning("Download page link not found on episode page.")
                    
                    # self.download_links.append(*season_download_links)
                    logger.info(f'Downloading { season_link.text}')

                    # asyncio.gather(*[await self.download(session, url.get('link'), url.get("name")) for url in season_download_links])
        except Exception as e:
            logger.critical(f"CODE BREAK = {e}")

        return super().scrape_site()


class MovieDownloader(Downloader):
    def __init__(self, movie_title, type='series', number_of_seasons=1):
        super().__init__(movie_title, type, number_of_seasons)

    async def scrape_site(self, session):
        return super().scrape_site()


async def main():
    if arguments.type == 'series':
        downloader = SeriesDownloader(arguments.title, number_of_seasons=arguments.number_of_seasons)
    elif arguments.type == 'movie':
        downloader = MovieDownloader(arguments.title)

    async with aiohttp.ClientSession() as session:
        await downloader.scrape_site(session)
        # print(downloader.download_links)
        tasks = [downloader.download(session, url.get("link"), url.get("name")) for url in downloader.download_links]
        # print(*tasks)
    
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
        