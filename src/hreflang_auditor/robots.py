"""robots.txt handling with one cached parser per origin."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, Optional, Tuple
from urllib.robotparser import RobotFileParser

from .urls import origin

#: ``fetch(url) -> (status, text)``; status is ``None`` on a network error.
RobotsFetcher = Callable[[str], Awaitable[Tuple[Optional[int], str]]]


class RobotsPolicy:
    """The parsed rules for one origin."""

    def __init__(self, parser: Optional[RobotFileParser], allow_all: bool, reason: str = "") -> None:
        self.parser = parser
        self.allow_all = allow_all
        self.reason = reason

    def can_fetch(self, agent: str, url: str) -> bool:
        if self.parser is None:
            return self.allow_all
        return self.parser.can_fetch(agent, url)


class RobotsCache:
    """Fetch robots.txt once per origin and answer ``allowed(url)``.

    Status handling follows Google's documented behaviour: a 4xx response means
    there are no restrictions, while a 5xx response or a network failure means
    the whole origin is treated as disallowed.
    """

    def __init__(self, fetcher: RobotsFetcher, agent: str) -> None:
        self._fetcher = fetcher
        self._agent = agent
        self._policies: Dict[str, RobotsPolicy] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def policy(self, url: str) -> RobotsPolicy:
        key = origin(url)
        if key in self._policies:
            return self._policies[key]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key not in self._policies:
                self._policies[key] = await self._load(key)
        return self._policies[key]

    async def allowed(self, url: str) -> bool:
        return (await self.policy(url)).can_fetch(self._agent, url)

    async def _load(self, key: str) -> RobotsPolicy:
        status, text = await self._fetcher(f"{key}/robots.txt")
        if status is None:
            return RobotsPolicy(None, allow_all=False, reason="robots.txt could not be fetched")
        if status >= 500:
            return RobotsPolicy(None, allow_all=False, reason=f"robots.txt returned {status}")
        if status >= 400:
            return RobotsPolicy(None, allow_all=True, reason=f"robots.txt returned {status}")
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return RobotsPolicy(parser, allow_all=True)
