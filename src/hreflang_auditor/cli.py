"""Command line interface: ``hreflang-auditor audit|check|rules``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import httpx

from . import codes
from . import rules as R
from ._version import __version__
from .auditor import AuditConfig, audit
from .baseline import Baseline, BaselineError
from .crawler import DEFAULT_USER_AGENT, CrawlConfig
from .langtag import parse_hreflang
from .models import Severity
from .reports import RENDERERS, render, render_annotations_csv
from .urls import ABSOLUTE, classify, host

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_USAGE = 2


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def _non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hreflang-auditor",
        description="Audit hreflang annotations from HTML, HTTP Link headers and XML sitemaps.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    a = sub.add_parser("audit", help="crawl URLs and/or sitemaps and report hreflang issues")
    a.add_argument("urls", nargs="*", help="page URLs to audit")
    a.add_argument("-s", "--sitemap", action="append", default=[], metavar="URL",
                   help="sitemap or sitemap index URL (repeatable)")
    a.add_argument("--sitemap-file", action="append", default=[], metavar="PATH",
                   help="local sitemap file, plain or .gz (repeatable)")
    a.add_argument("-i", "--input", metavar="PATH",
                   help="file with one URL per line ('-' for stdin); # starts a comment")
    a.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text")
    a.add_argument("-o", "--output", metavar="PATH", help="write the report here instead of stdout")
    a.add_argument("--annotations-csv", metavar="PATH",
                   help="also write every collected annotation to this CSV file")
    a.add_argument("-c", "--concurrency", type=_positive_int, default=5,
                   help="parallel requests (default 5)")
    a.add_argument("--timeout", type=_non_negative_float, default=15.0,
                   help="per-request timeout in seconds (default 15)")
    a.add_argument("--max-urls", type=_positive_int, default=500,
                   help="stop queueing new URLs after this many (default 500)")
    a.add_argument("--max-depth", type=_non_negative_int, default=3,
                   help="hreflang hops to follow from a seed (default 3)")
    a.add_argument("--max-sitemaps", type=_positive_int, default=50,
                   help="maximum sitemap files to fetch, including index children (default 50)")
    a.add_argument("--delay", type=_non_negative_float, default=0.0,
                   help="seconds to wait before each request (default 0)")
    a.add_argument("--retries", type=_non_negative_int, default=1,
                   help="retries for network errors, 429 and 5xx (default 1)")
    a.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    a.add_argument("--robots-agent", metavar="TOKEN",
                   help="user-agent token used for robots.txt matching "
                        "(default: first token of --user-agent)")
    a.add_argument("--ignore-robots", action="store_true",
                   help="do not fetch or obey robots.txt (only on sites you control)")
    a.add_argument("--no-follow", action="store_true",
                   help="only fetch the given URLs and sitemap entries, not hreflang targets")
    a.add_argument("--same-host", action="store_true",
                   help="only fetch URLs on the hosts of the seeds and sitemaps")
    a.add_argument("--insecure", action="store_true", help="do not verify TLS certificates")
    a.add_argument("--disable", action="append", default=[], metavar="RULE",
                   help="disable a rule (repeatable, comma-separated allowed)")
    a.add_argument("--severity", action="append", default=[], metavar="RULE=LEVEL",
                   help="override a rule's severity, e.g. missing-x-default=warning")
    a.add_argument("--min-severity", choices=[s.value for s in Severity], default="notice",
                   help="hide issues below this level (default notice)")
    a.add_argument("--fail-on", choices=["error", "warning", "notice", "never"], default="error",
                   help="exit with status 1 if an issue at or above this level exists")
    a.add_argument("--baseline", metavar="PATH",
                   help="hide issues recorded in this baseline (or JSON report); only new "
                        "issues are reported and count for --fail-on")
    a.add_argument("--write-baseline", metavar="PATH",
                   help="save the issues found by this run as a baseline file")
    a.add_argument("--fail-on-fixed", action="store_true",
                   help="with --baseline: also exit 1 when baseline issues are fixed, "
                        "so the baseline file gets refreshed")
    a.add_argument("-q", "--quiet", action="store_true", help="no progress output on stderr")

    c = sub.add_parser("check", help="validate hreflang values without crawling")
    c.add_argument("values", nargs="+", help="hreflang values, e.g. en-uk de-DE x-default")
    c.add_argument("--json", action="store_true", help="print JSON")

    r = sub.add_parser("rules", help="list every rule with its default severity")
    r.add_argument("--json", action="store_true", help="print JSON")
    return parser


def _read_urls(path: str) -> List[str]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text("utf-8")
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _split_rules(values: Sequence[str]) -> Set[str]:
    return {v.strip() for value in values for v in value.split(",") if v.strip()}


def _parse_overrides(values: Sequence[str]) -> Dict[str, Severity]:
    out: Dict[str, Severity] = {}
    for value in values:
        rule, sep, level = value.partition("=")
        if not sep:
            raise ValueError(f"--severity expects RULE=LEVEL, got {value!r}")
        out[rule.strip()] = Severity.parse(level.strip())
    return out


def _cmd_audit(args: argparse.Namespace, transport: Optional[httpx.AsyncBaseTransport] = None) -> int:
    urls = list(args.urls)
    if args.input:
        urls.extend(_read_urls(args.input))
    if not urls and not args.sitemap and not args.sitemap_file:
        print("error: give at least one URL, --input, --sitemap or --sitemap-file", file=sys.stderr)
        return EXIT_USAGE
    bad = [u for u in urls + args.sitemap if classify(u) != ABSOLUTE]
    if bad:
        print(f"error: not an absolute http(s) URL: {bad[0]}", file=sys.stderr)
        return EXIT_USAGE

    if args.fail_on_fixed and not args.baseline:
        print("error: --fail-on-fixed needs --baseline", file=sys.stderr)
        return EXIT_USAGE
    baseline: Optional[Baseline] = None
    if args.baseline:
        try:
            baseline = Baseline.load(args.baseline)
        except BaselineError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE

    allowed = None
    if args.same_host:
        allowed = {host(u) for u in urls + args.sitemap}
    crawl = CrawlConfig(
        concurrency=args.concurrency,
        timeout=args.timeout,
        max_urls=args.max_urls,
        max_depth=args.max_depth,
        max_sitemaps=args.max_sitemaps,
        delay=args.delay,
        retries=args.retries,
        user_agent=args.user_agent,
        robots_agent=args.robots_agent,
        respect_robots=not args.ignore_robots,
        follow_alternates=not args.no_follow,
        allowed_hosts=allowed,
        verify_tls=not args.insecure,
    )
    try:
        config = AuditConfig(
            crawl=crawl,
            disabled_rules=_split_rules(args.disable),
            severity_overrides=_parse_overrides(args.severity),
            min_severity=Severity.parse(args.min_severity),
        )
        config.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not args.quiet:
        print(
            f"Auditing {len(urls)} URL(s) and {len(args.sitemap) + len(args.sitemap_file)} "
            "sitemap(s)...",
            file=sys.stderr,
        )
    result = asyncio.run(
        audit(urls, args.sitemap, args.sitemap_file, config=config, transport=transport)
    )
    if args.write_baseline:
        Baseline.from_issues(result.issues).save(args.write_baseline)
        if not args.quiet:
            print(f"Baseline with {len(result.issues)} issue(s) written to {args.write_baseline}",
                  file=sys.stderr)
    if baseline is not None:
        result.apply_baseline(baseline)
    report = render(result, args.format)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"Report written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    if args.annotations_csv:
        Path(args.annotations_csv).write_text(render_annotations_csv(result), encoding="utf-8")

    if not args.quiet and args.output:
        c = result.counts
        print(f"{c['error']} error(s), {c['warning']} warning(s), {c['notice']} notice(s)",
              file=sys.stderr)
    if not args.quiet and result.baseline is not None:
        print(
            f"Baseline: {len(result.baseline.new)} new, {len(result.baseline.known)} known, "
            f"{len(result.baseline.fixed)} fixed",
            file=sys.stderr,
        )
    if args.fail_on != "never" and result.has_at_least(Severity.parse(args.fail_on)):
        return EXIT_ISSUES
    if args.fail_on_fixed and result.baseline is not None and result.baseline.fixed:
        return EXIT_ISSUES
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    results = []
    worst_invalid = False
    for value in args.values:
        code = parse_hreflang(value)
        worst_invalid = worst_invalid or not code.valid
        results.append(
            {
                "value": value,
                "valid": code.valid,
                "canonical": code.canonical if code.valid else None,
                "description": (
                    codes.describe(code.canonical) if code.valid and not code.is_x_default
                    else ("fallback for unmatched languages" if code.is_x_default else None)
                ),
                "findings": [
                    {
                        "rule": f.rule,
                        "severity": f.severity.value,
                        "message": f.message,
                        "suggestion": f.suggestion,
                    }
                    for f in code.findings
                ],
            }
        )
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for item in results:
            status = "ok     " if item["valid"] else "INVALID"
            label = f" -> {item['canonical']} ({item['description']})" if item["valid"] else ""
            print(f"{status} {item['value']}{label}")
            for f in item["findings"]:
                print(f"        {f['severity']}: {f['rule']}: {f['message']}")
    return EXIT_ISSUES if worst_invalid else EXIT_OK


def _cmd_rules(args: argparse.Namespace) -> int:
    rules = R.all_rules()
    if args.json:
        print(json.dumps(
            [{"id": r.id, "severity": r.severity.value, "category": r.category,
              "title": r.title, "help": r.help} for r in rules],
            indent=2,
        ))
        return EXIT_OK
    width = max(len(r.id) for r in rules)
    for rule in rules:
        print(f"{rule.id.ljust(width)}  {rule.severity.value:<7}  {rule.title}")
    return EXIT_OK


def main(
    argv: Optional[Sequence[str]] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> int:
    """Run the CLI. ``transport`` lets tests and embedders replace the network layer."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "audit":
        return _cmd_audit(args, transport)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "rules":
        return _cmd_rules(args)
    parser.print_help()
    return EXIT_USAGE
