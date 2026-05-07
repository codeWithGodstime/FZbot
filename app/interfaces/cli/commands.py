import argparse
import asyncio
import logging

from app.core.config import AppConfig
from app.core.orchestrator import DownloadOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A CLI utility program to download movies and series from MobileTVShows."
    )
    parser.add_argument("type", help="Movie or Series", choices=["movie", "series"])
    parser.add_argument("title", help="Name of movie/series you want to download")
    parser.add_argument(
        "-season",
        "--season",
        metavar="NS",
        type=int,
        help="Specify the season you want to download",
    )
    parser.add_argument(
        "-max_downloads",
        "--max_downloads",
        type=int,
        default=10,
        help="Restrict the number of episodes you want to download",
    )
    parser.add_argument(
        "-episode",
        "--episode",
        type=int,
        help="Restrict the number of episodes you want to download",
    )
    parser.add_argument(
        "-url",
        "--url",
        type=str,
        help="URL of the series you want to download",
    )
    parser.add_argument(
        "-concurrent",
        "--concurrent",
        type=int,
        default=3,
        help="Set the number of concurrent downloads",
    )
    return parser


async def run_cli(arguments: argparse.Namespace) -> None:
    config = AppConfig(
        title=arguments.title,
        media_type=arguments.type,
        season=arguments.season,
        max_downloads=arguments.max_downloads,
        specific_episode=arguments.episode,
        url=arguments.url,
        concurrent_downloads=arguments.concurrent,
        request_timeout_seconds=None,
    )
    orchestrator = DownloadOrchestrator(config=config)
    await orchestrator.run()


def entry() -> None:
    logging.basicConfig(level=logging.DEBUG)
    arguments = build_parser().parse_args()
    asyncio.run(run_cli(arguments))
