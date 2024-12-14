import logging
import asyncio
import aiohttp
import argparse

from downloader import SeriesDownloader, MovieDownloader

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

# TODO add feature to specify the specific episode or episodes user want to download, like 5 - 20
parser.add_argument(
    "-ne",
    "--number_of_episodes",
    type=int,
    default=1,
    help="Number of episode you want to download"
)

arguments = parser.parse_args()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__file__)

async def main():
    if arguments.type == 'series':
        downloader = SeriesDownloader(
            arguments.title, number_of_seasons=arguments.number_of_seasons, number_of_episodes=arguments.number_of_episodes)
    elif arguments.type == 'movie':
        downloader = MovieDownloader(arguments.title)

    timeout = aiohttp.ClientTimeout(total=0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await downloader.scrape_site(session)
        tasks = [downloader.download(session, url.get("link"), url.get(
            "name")) for url in downloader.download_links]

        print(tasks)
        # downloading
        for i in range(0, len(tasks), 5):
            batch = tasks[i:i + 5]
            await asyncio.gather(*batch, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
