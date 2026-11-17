# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Baselines for gradual adoption in CI. `audit --write-baseline PATH` records
  the issues of a run; `audit --baseline PATH` hides those known issues so only
  new ones are reported and count for `--fail-on`. Issues are matched by rule,
  page URL, hreflang value, target and source (not by message), as a multiset.
  Baseline issues that are gone are reported as fixed, and `--fail-on-fixed`
  turns them into a failing exit code. A `-f json` report is accepted as a
  baseline too.
- Baseline summary in the text, JSON (`baseline` object with `fixed_issues`) and
  HTML reports. The HTML language matrix still marks known problems.
- Python API: `Baseline`, `BaselineComparison`, `BaselineError`,
  `AuditResult.apply_baseline()` and `AuditResult.all_issues`.
- `CODE_OF_CONDUCT.md`, issue templates (bug report, feature request) and a pull
  request template.

### Changed

- Python 3.10 or newer is required, matching the versions tested in CI
  (3.10 to 3.13).

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
