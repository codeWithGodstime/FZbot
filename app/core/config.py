import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class AppConfig:
    title: str
    media_type: str
    season: int | None = None
    max_downloads: int | None = None
    specific_episode: int | None = None
    url: str | None = None
    concurrent_downloads: int = 5
    request_timeout_seconds: int | None = None
    titles: list[str] = field(default_factory=list)

    @property
    def output_dir(self) -> str:
        return self.title

    @property
    def movie_titles(self) -> list[str]:
        if self.titles:
            return self._dedupe_titles(self.titles)
        if self.title:
            return [self.title.strip()]
        return []

    @staticmethod
    def _dedupe_titles(titles: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for raw in titles:
            title = raw.strip()
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(title)
        return unique

    @staticmethod
    def parse_titles_text(text: str) -> list[str]:
        parts = re.split(r"[\n,]+", text)
        return AppConfig._dedupe_titles(parts)

    @staticmethod
    def format_batch_title(titles: list[str]) -> str:
        if not titles:
            return ""
        if len(titles) == 1:
            return titles[0]
        return f"{titles[0]} (+{len(titles) - 1} more)"
