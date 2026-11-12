"""Extract hreflang links, the canonical URL and robots directives from HTML."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional

# Elements that may appear in <head>. Anything else implicitly closes the head
# in an HTML parser, which is how Google ends up ignoring hreflang links that
# appear after, for example, an <img> injected into the head by a script.
_HEAD_ELEMENTS = frozenset(
    {"base", "link", "meta", "noscript", "script", "style", "template", "title", "head", "html"}
)
_ROBOT_NAMES = frozenset({"robots", "googlebot"})


@dataclass
class HtmlLink:
    hreflang: str
    href: str
    in_head: bool
    media: Optional[str] = None
    line: int = 0


@dataclass
class HtmlDocument:
    alternates: List[HtmlLink] = field(default_factory=list)
    canonicals: List[str] = field(default_factory=list)
    base_href: Optional[str] = None
    noindex: bool = False
    html_lang: Optional[str] = None
    head_closed_early: bool = False

    @property
    def canonical(self) -> Optional[str]:
        return self.canonicals[0] if self.canonicals else None


class _Extractor(HTMLParser):
    def __init__(self, robots_names) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = HtmlDocument()
        self.in_head = True
        self.robots_names = robots_names
        self._noscript_depth = 0

    def _attrs(self, attrs) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name, value in attrs:
            if name not in out:
                out[name.lower()] = value if value is not None else ""
        return out

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        a = self._attrs(attrs)
        if tag == "html" and "lang" in a and self.doc.html_lang is None:
            self.doc.html_lang = a["lang"].strip() or None
        if tag == "noscript":
            self._noscript_depth += 1
        if self.in_head and tag not in _HEAD_ELEMENTS and self._noscript_depth == 0:
            self.in_head = False
            if tag != "body":
                self.doc.head_closed_early = True
        if tag == "body":
            self.in_head = False
        if tag == "base" and "href" in a and self.doc.base_href is None:
            self.doc.base_href = a["href"].strip()
        elif tag == "link":
            self._link(a)
        elif tag == "meta" and self.in_head:
            name = a.get("name", "").strip().lower()
            if name in self.robots_names:
                content = a.get("content", "").lower()
                tokens = {t.strip() for t in content.replace(";", ",").split(",")}
                if "noindex" in tokens or "none" in tokens:
                    self.doc.noindex = True

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() == "noscript":
            self._noscript_depth = max(0, self._noscript_depth - 1)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "head":
            self.in_head = False
        elif tag == "noscript":
            self._noscript_depth = max(0, self._noscript_depth - 1)

    def _link(self, a: Dict[str, str]) -> None:
        rels = a.get("rel", "").lower().split()
        href = a.get("href")
        if href is None:
            return
        if "canonical" in rels and self.in_head:
            self.doc.canonicals.append(href.strip())
        if "alternate" in rels and "hreflang" in a:
            self.doc.alternates.append(
                HtmlLink(
                    hreflang=a["hreflang"],
                    href=href,
                    in_head=self.in_head,
                    media=a.get("media"),
                    line=self.getpos()[0],
                )
            )


def parse_html(text: str, user_agent_token: str = "googlebot") -> HtmlDocument:
    """Parse an HTML document. Never raises on malformed markup."""
    names = set(_ROBOT_NAMES)
    names.add(user_agent_token.lower())
    parser = _Extractor(frozenset(names))
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # pragma: no cover - html.parser is very lenient
        pass
    return parser.doc
