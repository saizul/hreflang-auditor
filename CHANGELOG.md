# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-12

### Added

- `hreflang-auditor audit` collects hreflang annotations from HTML `<link>`
  elements, HTTP `Link` headers and XML sitemaps (indexes and `.gz` included).
- Bundled ISO 639-1, ISO 3166-1 alpha-2 and ISO 15924 (subset) code tables.
- 41 rules covering code syntax and common mistakes (`en-uk`, `jp`, `es-419`,
  underscores, case), URL form, `<head>` placement, self-reference, return
  links, x-default, duplicates, cluster consistency, source disagreement and
  target status (non-200, redirect, noindex, canonical elsewhere, robots.txt).
- Async `httpx` crawler with a concurrency limit, retries, delay, URL budget,
  depth limit, body size cap and robots.txt support.
- Text, JSON, CSV and HTML (URL x language matrix) reports, plus an annotation
  CSV export.
- `hreflang-auditor check` to validate values offline and
  `hreflang-auditor rules` to list rules.
- Rule disabling, severity overrides, `--min-severity` and `--fail-on`.
- Python API (`audit`, `audit_sync`, `parse_hreflang`).
- Dockerfile and a workflow that publishes a multi-arch image to GHCR.

[Unreleased]: https://github.com/saizul/hreflang-auditor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/hreflang-auditor/releases/tag/v0.1.0
