from __future__ import annotations

import json

from ..auditor import AuditResult


def render_json(result: AuditResult) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
