import asyncio

from hreflang_auditor.robots import RobotsCache


def make(responses):
    calls = []

    async def fetch(url):
        calls.append(url)
        await asyncio.sleep(0)
        return responses[url]

    return fetch, calls


def run(coro):
    return asyncio.run(coro)


def test_rules_are_applied_and_cached():
    fetch, calls = make({"https://a.com/robots.txt": (200, "User-agent: *\nDisallow: /private/\n")})
    cache = RobotsCache(fetch, "hreflang-auditor")

    async def go():
        results = await asyncio.gather(
            cache.allowed("https://a.com/en/"),
            cache.allowed("https://a.com/private/x"),
            cache.allowed("https://a.com/de/"),
        )
        return results

    assert run(go()) == [True, False, True]
    assert calls == ["https://a.com/robots.txt"]


def test_agent_specific_group():
    body = "User-agent: hreflang-auditor\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    fetch, _ = make({"https://a.com/robots.txt": (200, body)})
    assert run(RobotsCache(fetch, "hreflang-auditor").allowed("https://a.com/x")) is False
    fetch, _ = make({"https://a.com/robots.txt": (200, body)})
    assert run(RobotsCache(fetch, "otherbot").allowed("https://a.com/x")) is True


def test_4xx_allows_everything():
    fetch, _ = make({"https://a.com/robots.txt": (404, "")})
    cache = RobotsCache(fetch, "x")
    assert run(cache.allowed("https://a.com/anything")) is True
    assert "404" in run(cache.policy("https://a.com/")).reason


def test_5xx_and_network_errors_disallow_everything():
    fetch, _ = make({"https://a.com/robots.txt": (503, ""), "https://b.com/robots.txt": (None, "")})
    cache = RobotsCache(fetch, "x")
    assert run(cache.allowed("https://a.com/x")) is False
    assert run(cache.allowed("https://b.com/x")) is False


def test_origins_are_separate():
    fetch, calls = make(
        {
            "https://a.com/robots.txt": (200, "User-agent: *\nDisallow: /\n"),
            "https://a.com:8443/robots.txt": (200, ""),
            "http://a.com/robots.txt": (200, ""),
        }
    )
    cache = RobotsCache(fetch, "x")
    assert run(cache.allowed("https://a.com/x")) is False
    assert run(cache.allowed("https://a.com:8443/x")) is True
    assert run(cache.allowed("http://a.com/x")) is True
    assert len(calls) == 3
