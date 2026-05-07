import argparse
import asyncio
import logging
import sys

def build_cli_parser() -> argparse.ArgumentParser:
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


def build_root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FZbot downloader with both CLI and browser UI modes."
    )
    subparsers = parser.add_subparsers(dest="command")

    cli_parser = subparsers.add_parser("cli", help="Run the terminal downloader")
    cli_arguments = build_cli_parser()
    for action in cli_arguments._actions:
        if action.dest == "help":
            continue
        cli_parser._add_action(action)

    ui_parser = subparsers.add_parser("ui", help="Run the local web UI")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the web UI to")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port for the web UI")

    return parser


async def run_cli(arguments: argparse.Namespace) -> None:
    from app.core.config import AppConfig
    from app.core.orchestrator import DownloadOrchestrator

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
    legacy_media_types = {"movie", "series"}

    if len(sys.argv) > 1 and sys.argv[1] in legacy_media_types:
        arguments = build_cli_parser().parse_args()
        asyncio.run(run_cli(arguments))
        return

    parser = build_root_parser()
    arguments = parser.parse_args()

    if arguments.command == "ui":
        from app.interfaces.ui.server import run_server

        run_server(host=arguments.host, port=arguments.port)
        return

    if arguments.command == "cli":
        asyncio.run(run_cli(arguments))
        return

    parser.print_help()
