# hreflang-auditor

[![CI](https://github.com/saizul/hreflang-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/hreflang-auditor/actions/workflows/ci.yml)
[![Container image](https://github.com/saizul/hreflang-auditor/actions/workflows/publish-image.yml/badge.svg)](https://github.com/saizul/hreflang-auditor/actions/workflows/publish-image.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Audit `hreflang` annotations the way search engines read them. `hreflang-auditor`
collects alternates from **HTML `<link>` tags**, **HTTP `Link` headers** and **XML
sitemaps (`xhtml:link`)**, crawls every target with an async, robots.txt-aware
crawler, and reports broken codes, missing return links, redirecting or
canonicalised targets and more as text, JSON, CSV or an HTML **URL x language
matrix**.

```console
$ hreflang-auditor audit https://shop.example/en/
https://shop.example/en/
  E known-mistake-region [html]: 'UK' is not an ISO 3166-1 code; use 'GB' (United Kingdom) (suggested: en-GB)
  E missing-return-link: https://shop.example/de/ (de) does not link back to this page; it links to https://shop.example/en instead (differs only by a trailing slash)
  E target-redirect: https://shop.example/es-old/ redirects (301) to https://shop.example/es/
  E target-canonical-mismatch: https://shop.example/pt/ declares canonical https://shop.example/en/
  E relative-url [html]: href '/fr/' is relative (resolves to https://shop.example/fr/)
  W mixed-protocol: set mixes http and https URLs; http: http://shop.example/
  ...
```

A full sample is in [`examples/sample-report.txt`](examples/sample-report.txt) and
[`examples/sample-report.html`](examples/sample-report.html).

## Features

- **Three sources, one model.** HTML `<link rel="alternate" hreflang>` (with
  `<base href>` support and detection of links that end up outside `<head>`),
  RFC 8288 `Link` headers (several headers, quoted commas, PDFs and other non-HTML
  files) and sitemaps, including sitemap indexes and `.xml.gz` files. Disagreement
  between sources is reported.
- **Code validation with bundled tables.** ISO 639-1 (183 languages), ISO 3166-1
  alpha-2 (249 regions) and common ISO 15924 scripts ship with the package as
  plain TSV files. No network lookups.
- **Common mistakes named and fixed.** `en-uk` (use `en-GB`), `jp` (use `ja`),
  `cn`, `dk`, `gr`, `ua`, withdrawn codes such as `iw`, region-only values (`gb`),
  `de_DE` underscores, UN M.49 regions (`es-419`), reserved codes (`EU`, `UN`, `XK`),
  three-letter languages and unconventional case (`EN-gb`), each with a suggestion.
- **Set checks.** Return-link reciprocity (with "near miss" hints for http/https,
  trailing slash and `www.` differences), self-reference, x-default presence,
  duplicate codes pointing at different URLs, one URL claimed by several
  languages, and clusters where versions disagree or are incomplete.
- **Target checks.** Alternates that return non-200, redirect, are `noindex` (meta
  robots or `X-Robots-Tag`), are canonicalised elsewhere (hreflang/canonical
  conflict), are blocked by robots.txt or cannot be fetched. Pages that carry
  hreflang but are themselves noindex or canonicalised elsewhere are flagged too.
- **URL checks.** Relative and protocol-relative hrefs, non-http(s) values and sets
  that mix http and https.
- **Polite async crawler.** `httpx` with a global concurrency limit, retries with
  backoff for 429/5xx/network errors, a per-request delay, a body size cap and a
  URL budget. robots.txt is fetched once per origin and obeyed by default.
  Redirects are recorded, not silently followed, so a redirecting hreflang target
  is reported precisely.
- **Reports.** Text for the terminal, JSON for pipelines, CSV for spreadsheets
  (with formula-injection protection) and a self-contained HTML report with a
  colour-coded URL x language matrix per cluster and a filterable issue list.
- **CI friendly.** `--fail-on` controls the exit code, every rule can be disabled
  or re-levelled, and the package has a Python API.
- **Generator.** `generate` turns a CSV mapping of your page versions into a
  sitemap with `xhtml:link` alternates, `<link>` tags per page or `Link` headers,
  after validating every value and URL, so the output is correct by construction.
- **Baselines.** Record the issues a site already has with `--write-baseline` and
  pass `--baseline` on later runs: only new issues are reported and fail the
  build, and issues fixed since the baseline are listed.

## Installation

Python 3.10 or newer.

```console
$ pip install git+https://github.com/saizul/hreflang-auditor.git
```

or from a clone:

```console
$ git clone https://github.com/saizul/hreflang-auditor.git
$ cd hreflang-auditor
$ python -m pip install .
```

The only runtime dependency is [httpx](https://www.python-httpx.org/).

## Usage

### Audit pages

```console
# One or more seed pages; hreflang targets are fetched automatically
$ hreflang-auditor audit https://example.com/en/ https://example.com/de/

# Seeds from a file (one URL per line, # comments allowed) or stdin
$ hreflang-auditor audit -i examples/urls.txt
$ cat urls.txt | hreflang-auditor audit -i -
```

### Audit a sitemap

```console
# Sitemap or sitemap index, plain or gzipped (repeatable)
$ hreflang-auditor audit --sitemap https://example.com/sitemap_index.xml

# A local file, e.g. before deploying a generated sitemap
$ hreflang-auditor audit --sitemap-file build/sitemap.xml --no-follow
```

Every `<loc>` is fetched so its status, canonical and robots directives can be
checked, and so annotations in the page HTML can be compared with the sitemap.

### Reports

```console
$ hreflang-auditor audit https://example.com/en/ -f html -o hreflang-report.html
$ hreflang-auditor audit https://example.com/en/ -f json > report.json
$ hreflang-auditor audit https://example.com/en/ -f csv  -o issues.csv
$ hreflang-auditor audit https://example.com/en/ --annotations-csv annotations.csv
```

| Format | Content |
| ------ | ------- |
| `text` (default) | summary, issues grouped by URL, counts per rule |
| `json` | summary, issues, every page with status/canonical/noindex, every annotation, clusters |
| `csv` | one row per issue: `severity,rule,url,hreflang,target,source,message` |
| `html` | summary cards, a URL x language matrix per cluster, a filterable issue table |

In the HTML matrix each row is a URL and each column an hreflang value. A cell
shows what that URL declares for that value: `self`, `ok` (reciprocal),
`no return`, `target` (the target has a status, noindex or canonical problem),
`missing` (other versions declare it, this one does not), `conflict` (several
URLs for one value) or `?` (target not crawled). Hover a cell for the URL.

### Baselines: only fail on new issues

Large sites rarely start with a clean hreflang setup. A baseline lets you adopt
the auditor in CI without fixing everything first: record today's issues once,
commit the file, and from then on only issues that are not in the baseline are
reported and counted for `--fail-on`.

```console
$ hreflang-auditor audit -s https://example.com/sitemap.xml --write-baseline hreflang-baseline.json --fail-on never
$ hreflang-auditor audit -s https://example.com/sitemap.xml --baseline hreflang-baseline.json
Baseline: 2 new, 41 known (hidden), 3 fixed since the baseline
```

- An issue is matched by its rule id, page URL, hreflang value, target URL and
  source. The message text and the severity are not part of the match, so
  rewording or re-levelling a rule does not break a baseline.
- Matching counts occurrences: if the baseline holds one issue and the audit now
  finds the same issue twice, one of them is new.
- Baseline issues that are no longer found are reported as *fixed* (text and
  HTML summary, `baseline.fixed_issues` in JSON). Add `--fail-on-fixed` to exit
  with 1 in that case too, which reminds you to refresh the committed baseline.
- A JSON report (`-f json`) from an earlier run is accepted as a baseline as well.
- The HTML language matrix keeps marking known problems; only the issue table
  and the counts are limited to new issues.
- `--write-baseline` saves the issues after `--disable`, `--severity` and
  `--min-severity` are applied. Use the same options on later runs; otherwise
  issues of a rule you disabled show up as "fixed".
- Passing both options compares against the old baseline and writes a fresh
  one with every current issue, which is a convenient way to ratchet.

The baseline file is plain, sorted JSON so changes are easy to review:

```json
{
  "kind": "hreflang-auditor-baseline",
  "format": 1,
  "tool": "hreflang-auditor",
  "version": "0.1.0",
  "created_at": "2026-11-17T09:30:00+00:00",
  "issues": [
    {
      "fingerprint": "5d0c1b9e8f7a6b2c4d3e",
      "rule": "missing-return-link",
      "severity": "error",
      "url": "https://example.com/en/",
      "hreflang": "de",
      "target": "https://example.com/de/",
      "source": "html",
      "message": "..."
    }
  ]
}
```

### Check codes without crawling

```console
$ hreflang-auditor check en-uk EN-gb es-419 zh-Hant-TW x-default
INVALID en-uk
        error: known-mistake-region: 'UK' is not an ISO 3166-1 code; use 'GB' (United Kingdom)
ok      EN-gb -> en-GB (English (United Kingdom))
        notice: non-canonical-case: 'EN-gb' works (values are case-insensitive) but the conventional form is 'en-GB'
INVALID es-419
        error: unsupported-region: '419' is a UN M.49 area code; Google only supports ISO 3166-1 alpha-2 regions, so use the language alone or list each country
ok      zh-Hant-TW -> zh-Hant-TW (Chinese (Han (Traditional), Taiwan))
ok      x-default -> x-default (fallback for unmatched languages)
```

`check` exits with 1 if any value is invalid; add `--json` for machine output.

### Generate annotations from a mapping

Keep the versions of each page in a spreadsheet and let the tool write the
annotations. Two CSV layouts are accepted (comma, semicolon or tab separated):

```text
page,en-GB,en-US,de-DE,fr                        group,hreflang,url
home,https://example.com/en-gb/,...              home,en-GB,https://example.com/en-gb/
pricing,https://example.com/en-gb/pricing/,...   home,de-DE,https://example.com/de/
```

In the wide layout (left) each row is one set of alternates and each column an
hreflang value; empty cells are skipped. In the long layout (right) rows with the
same `group` belong together. See [`examples/hreflang-map.csv`](examples/hreflang-map.csv).

```console
$ hreflang-auditor generate examples/hreflang-map.csv -o sitemap-hreflang.xml --x-default en-GB
wrote sitemap-hreflang.xml: 11 page(s) in 3 group(s)
$ hreflang-auditor generate examples/hreflang-map.csv -f html      # <link> tags per page
$ hreflang-auditor generate examples/hreflang-map.csv -f headers   # HTTP Link headers (PDFs)
$ hreflang-auditor generate examples/hreflang-map.csv -f json      # {url: [{hreflang, href}]}
```

Every page gets the complete set, itself included, so return links and
self-references are always right. Values are written in conventional case
(`en-gb` becomes `en-GB`). `--x-default VALUE` adds an x-default that points
at that value's URL in every group without one.

Before anything is written, the mapping is checked: invalid values (`en-uk`,
`jp`, ...), relative or non-http(s) URLs, two URLs for one value in a group, and
a URL that appears in two groups are errors, reported with their line number;
the command then exits with 1 and writes nothing. Groups with a single URL and
more than 50,000 URLs (the sitemap limit) are warnings.

### List the rules

```console
$ hreflang-auditor rules          # id, default severity, title
$ hreflang-auditor rules --json   # includes the help text
```

## Configuration

All options of `hreflang-auditor audit`:

| Option | Default | Meaning |
| ------ | ------- | ------- |
| `-s, --sitemap URL` | | sitemap or index URL (repeatable) |
| `--sitemap-file PATH` | | local sitemap file (repeatable) |
| `-i, --input PATH` | | file with seed URLs, `-` for stdin |
| `-f, --format` | `text` | `text`, `json`, `csv`, `html` |
| `-o, --output PATH` | stdout | write the report to a file |
| `--annotations-csv PATH` | | also export every annotation |
| `-c, --concurrency N` | 5 | requests in flight at once |
| `--timeout S` | 15 | per-request timeout |
| `--max-urls N` | 500 | URL budget; further URLs are counted as skipped |
| `--max-depth N` | 3 | hreflang hops followed from a seed |
| `--max-sitemaps N` | 50 | sitemap files fetched, index children included |
| `--delay S` | 0 | pause before each request |
| `--retries N` | 1 | retries for network errors, 429 and 5xx |
| `--user-agent UA` | `hreflang-auditor/0.1.0 (+repo URL)` | request User-Agent |
| `--robots-agent TOKEN` | first token of the UA | token matched against robots.txt groups, e.g. `Googlebot` |
| `--ignore-robots` | off | do not fetch or obey robots.txt (only on sites you run) |
| `--no-follow` | off | do not fetch hreflang targets |
| `--same-host` | off | only fetch hosts of the seeds/sitemaps |
| `--insecure` | off | skip TLS verification (staging sites) |
| `--disable RULE[,RULE]` | | turn rules off (repeatable) |
| `--severity RULE=LEVEL` | | change a rule's level to `error`, `warning` or `notice` |
| `--min-severity LEVEL` | `notice` | hide lower levels |
| `--fail-on LEVEL` | `error` | exit 1 if an issue at this level or above exists; `never` always exits 0 |
| `--baseline PATH` | | hide issues recorded in a baseline or JSON report; only new ones are reported and counted |
| `--write-baseline PATH` | | save the issues of this run as a baseline file |
| `--fail-on-fixed` | off | with `--baseline`: also exit 1 when baseline issues are gone |
| `-q, --quiet` | off | no progress output on stderr |

Exit codes: `0` no blocking issues, `1` issues at or above `--fail-on` (or
invalid values for `check`, or fixed baseline issues with `--fail-on-fixed`),
`2` usage errors (including an unreadable baseline file).

### Rules

| Rule | Level | What it means |
| ---- | ----- | ------------- |
| `invalid-format` | error | not `x-default` or `language[-Script][-REGION]` |
| `underscore-separator` | error | `en_US` instead of `en-US` |
| `invalid-language` | error | first subtag is not ISO 639-1 |
| `three-letter-language` | error | `eng`, `deu`, ... |
| `region-only` | error | a country code with no language (`gb`) |
| `known-mistake-language` | error | `jp`, `cn`, `dk`, `gr`, `ua`, `iw`, ... |
| `suspicious-language` | warning | valid but likely unintended: `kr`, `se`, `ee`, `my` |
| `invalid-region` | error | region is not ISO 3166-1 alpha-2 |
| `known-mistake-region` | error | `UK` (use `GB`), `EL` (use `GR`) |
| `reserved-region` | error | `EU`, `UN`, `XK` and other reserved codes |
| `unsupported-region` | error | numeric UN M.49 regions such as `419` |
| `unknown-script` | warning | script subtag not in the bundled ISO 15924 list |
| `non-canonical-case` | notice | works, but conventionally `en-GB`, `zh-Hant`, `x-default` |
| `code-whitespace` | warning | spaces around the value |
| `relative-url` | error | href is relative |
| `protocol-relative-url` | error | href starts with `//` |
| `invalid-url` | error | empty or non-http(s) href |
| `mixed-protocol` | warning | a set mixes http and https URLs |
| `link-outside-head` | error | `<link>` ended up outside `<head>` and is ignored |
| `media-attribute` | warning | hreflang combined with `media` on one `<link>` |
| `missing-self-reference` | warning | the set does not list the page itself |
| `missing-return-link` | error | target does not link back |
| `missing-x-default` | notice | no x-default |
| `duplicate-hreflang` | error | one value, several URLs on one page |
| `duplicate-annotation` | notice | the same pair declared twice |
| `one-url-many-languages` | notice | one URL claimed by different languages |
| `inconsistent-set` | warning | page lacks versions declared elsewhere in its cluster |
| `cluster-code-conflict` | warning | versions disagree on the URL for a value |
| `conflicting-sources` | warning | HTML, headers and sitemap disagree for a page |
| `target-non-200` | error | target returns 4xx/5xx |
| `target-redirect` | error | target redirects |
| `target-noindex` | error | target is noindex |
| `target-canonical-mismatch` | error | target's canonical points elsewhere |
| `target-unreachable` | warning | network/TLS/timeout error |
| `target-blocked` | warning | target disallowed by robots.txt |
| `page-canonical-conflict` | error | a page with hreflang is canonicalised elsewhere |
| `page-noindex` | warning | a page with hreflang is noindex |
| `html-lang-mismatch` | notice | target's `<html lang>` names another language |
| `sitemap-error` | error | sitemap failed to download or parse |
| `sitemap-warning` | warning | wrong namespaces, unknown root element |
| `robots-unavailable` | notice | robots.txt returned 4xx/5xx or failed |

### How the rules map to Google's documentation

The checks follow Google Search Central's
[Tell Google about localized versions of your page](https://developers.google.com/search/docs/specialty/international/localized-versions):

- The three methods (HTML, HTTP headers, sitemap) are equivalent; the tool reads
  all three and warns when they disagree.
- Language codes are ISO 639-1, optionally followed by an ISO 15924 script and/or
  an ISO 3166-1 alpha-2 region. A region on its own is not allowed. Codes outside
  those standards, such as `es-419`, are not supported.
- Values are case-insensitive, so wrong case is only a notice.
- Each version must list itself and every other version, and links must be
  bidirectional, otherwise they may be ignored.
- Alternate URLs must be fully qualified, including the protocol.
- `<link>` elements are only read inside a well-formed `<head>`, and hreflang
  should not be combined with other attributes such as `media` in one tag.
- In sitemaps, alternates are `xhtml:link` children of `<url>` in the
  `http://www.w3.org/1999/xhtml` namespace.
- x-default marks the fallback page for unmatched languages.

The target-status checks (non-200, redirect, noindex, canonical elsewhere) and
`html-lang-mismatch` are widely used best practice rather than statements from
that page: Google documents elsewhere that it uses canonical URLs and does not use
the `lang` attribute to detect language, which is why `html-lang-mismatch` is only
a notice.

## Examples

**CI gate for a staging deploy** (fail on errors, hide notices, quiet):

```yaml
- run: pip install git+https://github.com/saizul/hreflang-auditor.git
- run: >
    hreflang-auditor audit --sitemap https://staging.example.com/sitemap.xml
    --min-severity warning --fail-on error -q -f html -o hreflang.html
- uses: actions/upload-artifact@v4
  if: always()
  with: { name: hreflang-report, path: hreflang.html }
```

**Treat a missing x-default as a warning and ignore `html lang`:**

```console
$ hreflang-auditor audit https://example.com/ --severity missing-x-default=warning \
    --disable html-lang-mismatch
```

**Evaluate robots.txt as Googlebot would, slowly:**

```console
$ hreflang-auditor audit -s https://example.com/sitemap.xml --robots-agent Googlebot \
    --concurrency 2 --delay 0.5
```

**Only the issues, as JSON, with jq:**

```console
$ hreflang-auditor audit https://example.com/en/ -f json -q \
    | jq -r '.issues[] | select(.severity=="error") | "\(.rule)\t\(.url)\t\(.target)"'
```

### Python API

```python
from hreflang_auditor import AuditConfig, audit_sync
from hreflang_auditor.crawler import CrawlConfig
from hreflang_auditor.reports import render

config = AuditConfig(crawl=CrawlConfig(concurrency=3, max_urls=200))
result = audit_sync(["https://example.com/en/"], config=config)

print(result.counts)            # {'error': 2, 'warning': 1, 'notice': 0}
for issue in result.issues:
    print(issue.severity.value, issue.rule, issue.url, issue.message)
open("report.html", "w").write(render(result, "html"))
```

To apply a baseline from Python, load it and call `apply_baseline()` on the
result; `result.issues` then holds only new issues and `result.baseline` the
comparison:

```python
from hreflang_auditor import Baseline

result.apply_baseline(Baseline.load("hreflang-baseline.json"))
print(len(result.baseline.new), len(result.baseline.known), len(result.baseline.fixed))
Baseline.from_issues(result.all_issues).save("hreflang-baseline.json")  # refresh
```

`audit()` is the async version. Both accept `transport=` (any
`httpx.AsyncBaseTransport`), which is how the test suite runs whole sites from
memory. `hreflang_auditor.parse_hreflang("en-uk")` validates a single value.

## Docker image

A multi-arch image (linux/amd64, linux/arm64) is published to GitHub Packages by
[`publish-image.yml`](.github/workflows/publish-image.yml) on every push to `main`
and on releases:

```bash
docker pull ghcr.io/saizul/hreflang-auditor:latest
docker run --rm ghcr.io/saizul/hreflang-auditor:latest check en-uk de-DE
docker run --rm -v "$PWD:/work" ghcr.io/saizul/hreflang-auditor:latest \
  audit https://example.com/en/ -f html -o /work/hreflang-report.html
```

Mount a folder at `/work` to read local sitemap files or write reports. The
container runs as an unprivileged user. Release tags are also published as
`ghcr.io/saizul/hreflang-auditor:<version>`.

## Testing

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e ".[dev]"
$ pytest
$ ruff check .
```

The tests never touch the network. `tests/conftest.py` serves fixture sites from
`tests/fixtures/sites/<name>/routes.json` through `httpx.MockTransport`:

| Fixture | What it covers |
| ------- | -------------- |
| `good` | a clean four-version cluster with x-default and canonicals: zero issues |
| `broken` | `en-uk`, duplicates, relative and protocol-relative hrefs, a link in `<body>`, redirects, 404, noindex, canonical elsewhere, robots.txt block, http/https mix, missing return links |
| `headers` | `Link` headers on PDFs (several headers, several values) and header/HTML disagreement |
| `sitemap` | a sitemap index with a gzipped child, a wrong xhtml namespace, a 404 child and a missing self-reference |

CI runs the suite on Python 3.10 to 3.13, lints with ruff, smoke-tests the console
script and installs the built wheel to make sure the code tables are packaged.

## Limitations

- **No JavaScript rendering.** Annotations injected by client-side JavaScript are
  not seen. Google can render JavaScript, so a page may be fine for Google and
  still show as missing here (the reverse is rarer).
- **Only hreflang links are followed.** This is not a general site crawler. Use
  sitemaps or `--input` to cover a whole site; `--max-urls` caps the run.
- **Return links are checked only where the target's full set is known**: the
  target was fetched with 200 or has sitemap annotations. Targets skipped by the
  URL budget, depth limit or `--no-follow` are not reported as missing.
- **Google behaviour is approximated.** Rules are based on the public
  documentation; how Google weighs a partially broken cluster is not public.
  `--ignore-robots` exists for your own sites only.
- **robots.txt semantics** come from Python's `urllib.robotparser`, which does not
  implement every extension Google supports (for example `*` and `$` wildcards
  inside paths are matched literally). A 5xx or unreachable robots.txt blocks the
  origin, as Google does.
- **Code tables are static.** The ISO tables were compiled for this release; the
  script list is a curated subset, so an unknown script is only a warning.
- **Sitemaps** larger than 60 MB uncompressed, and XML with entity declarations,
  are rejected.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).
Security reports: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) - Copyright (c) 2026 Saizul Amin ([saizul.com](https://saizul.com)).
