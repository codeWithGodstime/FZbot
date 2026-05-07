from dataclasses import dataclass


@dataclass(slots=True)
class DownloadItem:
    name: str
    url: str
