from dataclasses import dataclass


@dataclass(slots=True)
class DownloadItem:
    name: str
    url: str
    subdir: str | None = None


@dataclass(slots=True)
class DownloadEvent:
    name: str
    status: str
    downloaded_bytes: int = 0
    total_bytes: int = 0
    detail: str | None = None
