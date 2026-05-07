from dataclasses import dataclass


@dataclass(slots=True)
class AppConfig:
    title: str
    media_type: str
    season: int | None = None
    max_downloads: int | None = None
    specific_episode: int | None = None
    url: str | None = None
    concurrent_downloads: int = 3
    request_timeout_seconds: int | None = None

    @property
    def output_dir(self) -> str:
        return self.title
