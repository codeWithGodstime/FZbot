from dataclasses import dataclass


@dataclass(slots=True)
class DownloadItem:
    name: str
    url: str


@dataclass(slots=True)
class DownloadEvent:
    name: str
    status: str
    downloaded_bytes: int = 0
    total_bytes: int = 0
    detail: str | None = None
