"""Render the reports for the "broken" test fixture site into examples/.

Run from the repository root:  python examples/make_sample_report.py
No network access is needed: the fixture site is served from memory.
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import FixtureSite, fast_config  # noqa: E402

from hreflang_auditor.auditor import audit  # noqa: E402
from hreflang_auditor.reports import render  # noqa: E402


def main() -> None:
    site = FixtureSite.load("broken")
    result = asyncio.run(
        audit(["https://shop.test/en/"], config=fast_config(), transport=site.transport())
    )
    out = ROOT / "examples"
    for fmt, name in (("html", "sample-report.html"), ("text", "sample-report.txt")):
        (out / name).write_text(render(result, fmt), encoding="utf-8")
        print(f"wrote examples/{name}")


if __name__ == "__main__":
    main()
