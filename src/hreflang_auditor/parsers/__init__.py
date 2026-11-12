"""Extract hreflang data from HTML documents, HTTP headers and XML sitemaps."""

from .headers import LinkValue, parse_link_header, parse_x_robots_tag
from .html import HtmlDocument, parse_html
from .sitemap import SitemapError, parse_sitemap

__all__ = [
    "HtmlDocument",
    "LinkValue",
    "SitemapError",
    "parse_html",
    "parse_link_header",
    "parse_sitemap",
    "parse_x_robots_tag",
]
