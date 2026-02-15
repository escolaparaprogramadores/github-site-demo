# ============================================================
# AI ENGINEERING PLATFORM - STABLE VERSION
# ============================================================

import json
import os
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from prompt_templates import build_review_prompt, AI_FEATURE_FLAGS
from logger import (
    info, success, warning,
    operation_start, operation_success,
    operation_failed, operation_skipped
)

GH_API = "https://api.github.com"
OAI_API = "https://api.openai.com/v1/chat/completions"


# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

def _validate_environment():
    operation_start("Validação de ambiente")

    repo = (os.environ.get("REPO") or "").strip()
    gh_token = (os.environ.get("GH_TOKEN") or "").strip()
    pr_sha = (os.environ.get("PR_SHA") or "").strip()
    pr_number_raw = (os.environ.get("PR_NUMBER") or "").strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()

    required = [repo, gh_token, pr_sha, pr_number_raw, openai_key]

    if not all(required):
        operation_failed("Validação", "Configuração ausente")
        raise SystemExit(1)

    if not pr_number_raw.isdigit():
        operation_failed("Validação", "PR_NUMBER inválido")
        raise SystemExit(1)

    pr_number = int(pr_number_raw)
    operation_success("Validação", f"PR #{pr_number}")

    return repo, gh_token, pr_sha, pr_number, openai_key


# ============================================================
# HTTP UTILITIES
# ============================================================

def _calculate_retry_wait(attempt, retry_after_header=None):
    if retry_after_header:
        try:
            return min(int(retry_after_header), 60)
        except Exception:
            pass
    return min((2 ** attempt) + random.uniform(0, 2), 60)


def _should_retry_http_error(status_code):
    return status_code in (429, 500, 502, 503, 504)


def http_json(url, method="GET", headers=None, body=None, max_attempts=6):
    headers = headers or {}

    for attempt in range(1, max_attempts + 1):
        try:
            req = Request(url, method=method, headers=headers, data=body)
            with urlopen(req, timeout=60) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data) if data else None
        except HTTPError as e:
            if not _should_retry_http_error(e.code):
                raise
            wait = _calculate_retry_wait(attempt, e.headers.get("Retry-After"))
            time.sleep(wait)
        except URLError:
            wait = _calculate_retry_wait(attempt)
            time.sleep(wait)

    raise RuntimeError("Request failed after retries")


def gh_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-engineering-platform"
    }


def oai_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


# ============================================================
# PATCH PARSER
# ============================================================

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_right_lines_from_patch(patch: str):
    changed = set()
    if not patch:
        return changed

    right_line = None

    for raw in patch.splitlines():
        m = HUNK_RE.match(raw)
        if m:
            right_line = int(m.group(1))
            continue

        if right_line is None:
            continue

        if raw.startswith(" "):
            right_line += 1
        elif raw.startswith("+") and not raw.startswith("+++"):
            changed.add(right_line)
            right_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        else:
            right_line += 1

    return changed


# ============================================================
# SUGGESTION HELPERS
# ============================================================

def _ensure_valid_suggestion(body: str):
    body = body.strip()

    if "```suggestion" not in body:
        return body

    if not body.rstrip().endswith("```"):
        body = body.rstrip() + "\n```"

    return body


def _force_fallback_suggestion(path, eligible_lines):
    """
    Gera suggestion automática para garantir botão Apply.
    """
    return [{
        "path": path,
        "line": eligible_lines[0],
        "side": "RIGHT",
        "body": """Sugestão: Pequena melhoria automática

```suggestion
# TODO: Revisar este trecho para melhorar clareza
```"""
    }]