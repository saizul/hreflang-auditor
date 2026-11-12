# Contributing

Thanks for taking the time to improve hreflang-auditor. Bug reports, new checks,
corrections to the code tables and documentation fixes are all welcome.

## Reporting a bug

Open an issue with:

- the command you ran and the full output or traceback
- your Python version (`python --version`) and operating system
- the smallest HTML snippet, `Link` header or sitemap fragment that reproduces
  the problem. Replace real domains with `example.com` if the site is private.

For false positives, please quote the part of Google's documentation that you
think the rule contradicts.

## Development setup

You need Python 3.9 or newer.

```console
$ git clone https://github.com/saizul/hreflang-auditor.git
$ cd hreflang-auditor
$ python -m venv .venv
$ . .venv/bin/activate
$ python -m pip install -e ".[dev]"
$ pytest
$ ruff check .
```

## Project layout

| Path | Purpose |
| ---- | ------- |
| `src/hreflang_auditor/langtag.py` | parse and validate one hreflang value |
| `src/hreflang_auditor/codes.py`, `data/*.tsv` | ISO code tables and known mistakes |
| `src/hreflang_auditor/parsers/` | HTML, `Link`/`X-Robots-Tag` header and sitemap parsers |
| `src/hreflang_auditor/crawler.py`, `robots.py` | async crawler and robots.txt cache |
| `src/hreflang_auditor/rules.py` | rule registry (ids, default levels, help text) |
| `src/hreflang_auditor/checks.py` | the checks that produce issues |
| `src/hreflang_auditor/reports/` | text, JSON, CSV and HTML renderers |
| `tests/fixtures/sites/` | fixture websites served by a mocked transport |

## Adding a rule

1. Register it in `rules.py` with a stable, kebab-case id, a default level and a
   one-sentence help text.
2. Emit it from a check in `checks.py` (or from `langtag.py` for value rules).
3. Add a unit test in `tests/test_checks.py` and, if it needs HTTP, a route in a
   fixture site plus an assertion in `tests/test_audit_sites.py`.
4. Document it in the rule table in `README.md` and in `CHANGELOG.md`.

Rule ids are part of the public interface (users disable them by id), so do not
rename existing ones.

## Updating code tables

The tables in `src/hreflang_auditor/data/` are tab-separated `code<TAB>name`
files. Keep them sorted, cite the source of the change in the pull request and
update the counts asserted in `tests/test_codes.py`.

## Pull requests

- Keep changes focused; one feature or fix per pull request.
- Tests must not use the network. Use `FixtureSite` from `tests/conftest.py`.
- Run `pytest` and `ruff check .` before pushing. CI runs both on Python 3.9-3.12.
- Add an entry under "Unreleased" in `CHANGELOG.md`.

By contributing you agree that your contribution is licensed under the MIT
License of this project.
