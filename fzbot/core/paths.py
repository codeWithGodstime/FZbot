import os
import sys
from pathlib import Path


def default_download_root() -> Path:
    xdg_videos = os.environ.get("XDG_VIDEOS_DIR")
    if xdg_videos:
        return Path(xdg_videos) / "fzbot"
    if sys.platform == "darwin":
        return Path.home() / "Movies" / "fzbot"
    return Path.home() / "Videos" / "fzbot"
