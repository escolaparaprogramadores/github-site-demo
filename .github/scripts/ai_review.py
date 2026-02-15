# ============================================================
# AI ENGINEERING PLATFORM - ENTERPRISE VERSION (FIXED)
# ============================================================

import json
import os
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ========================
# CONFIG
# ========================

GH_API = "https://api.github.com"
OAI_API = "https://api.openai.com/v1/chat/completions"

AI_FEATURE_FLAGS = {
    "REVIEW_ENABLED": True,
    "SUGGESTIONS_ENABLED": True,
    "MAX_COMMENTS_PER_FILE": 3
}

# ========================
# ENV VALIDATION
# ========================

def _validate_environment():
    repo = os.environ.get("REPO")
    token = os.environ.get("GH_TOKEN")
    pr_sha = os.environ.get("PR_SHA")
    pr_number = os.environ.get("PR_NUMBER")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not all([repo, token, pr_sha, pr_number, openai_key]):
        raise RuntimeError("Missing environment variables")

    return repo, token, pr_sha, int(pr_number), openai_key


# ========================
# HTTP UTIL
# ========================

def http_json(url, method="GET", headers=None, body=None):
    req = Request(url, method=method, headers=headers or {}, data=body)
    with urlopen(req, timeout=60) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data) if data else None


def gh_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }


def oai_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


# ========================
# PATCH PARSER
# ========================

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_right_lines_from_patch(patch):
    changed = set()
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


# ========================
# OPENAI CALL
# ========================

def call_openai(prompt, api_key):
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Responda somente JSON válido."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }

    return http_json(
        OAI_API,
        method="POST",
        headers=oai_headers(api_key),
        body=json.dumps(payload).encode("utf-8")
    )


# ========================
# FILE FETCH
# ========================

def fetch_pr_files(repo, token, pr_number):
    url = f"{GH_API}/repos/{repo}/pulls/{pr_number}/files"
    files = http_json(url, headers=gh_headers(token)) or []

    selected = []
    for f in files:
        if f.get("patch"):
            selected.append({
                "path": f["filename"],
                "patch": f["patch"]
            })

    return selected


# ========================
# REVIEW PROCESS
# ========================

def process_file_review(path, patch, openai_key):
    eligible_lines = sorted(list(changed_right_lines_from_patch(patch)))
    if not eligible_lines:
        return []

    prompt = f"Revise o seguinte diff:\n{patch}"

    data = call_openai(prompt, openai_key)

    content = data["choices"][0]["message"]["content"]

    try:
        obj = json.loads(content)
    except Exception:
        return []

    comments = []

    for c in obj.get("comments", [])[:3]:
        comments.append({
            "path": path,
            "line": eligible_lines[0],
            "side": "RIGHT",
            "body": c.get("body", "Sugestão automática")
        })

    return comments


# ========================
# PUBLISH REVIEW
# ========================

def publish_review(repo, token, pr_sha, pr_number, comments):
    if not comments:
        return

    review_payload = {
        "commit_id": pr_sha,
        "event": "COMMENT",
        "comments": comments
    }

    url = f"{GH_API}/repos/{repo}/pulls/{pr_number}/reviews"

    http_json(
        url,
        method="POST",
        headers=gh_headers(token),
        body=json.dumps(review_payload).encode("utf-8")
    )


# ========================
# MAIN
# ========================

def main():
    repo, token, pr_sha, pr_number, openai_key = _validate_environment()

    files = fetch_pr_files(repo, token, pr_number)

    all_comments = []

    for f in files:
        comments = process_file_review(
            f["path"],
            f["patch"],
            openai_key
        )
        all_comments.extend(comments)

    publish_review(repo, token, pr_sha, pr_number, all_comments)

    print("AI Review finalizado com sucesso")


if __name__ == "__main__":
    main()
