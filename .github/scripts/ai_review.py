# ============================================================
# AI ENGINEERING PLATFORM - STABLE VERSION (FIXED)
# ============================================================

import json
import os
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prompt_templates import build_review_prompt

GH_API = "https://api.github.com"
OAI_API = "https://api.openai.com/v1/responses"


# ========================
# ENV
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
# HTTP
# ========================

def http_json(url, method="GET", headers=None, body=None):
    req = Request(url, method=method, headers=headers or {}, data=body)

    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else None
    except HTTPError as e:
        print("HTTP ERROR:", e.code)
        print(e.read().decode())
        raise


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

    return sorted(list(changed))


# ========================
# OPENAI
# ========================

def extract_text_from_response(data):
    """
    Extrai texto de forma segura da Responses API
    """
    try:
        return data["output"][0]["content"][0]["text"]
    except Exception:
        print("Resposta inesperada da OpenAI:")
        print(json.dumps(data, indent=2))
        return None


def call_openai(prompt, api_key):
    payload = {
        "model": "gpt-4.1-mini",
        "input": prompt,
        "text": {
            "format": {
                "type": "json_object"
            }
        }
    }

    return http_json(
        OAI_API,
        method="POST",
        headers=oai_headers(api_key),
        body=json.dumps(payload).encode("utf-8")
    )


# ========================
# FETCH FILES
# ========================

def fetch_pr_files(repo, token, pr_number):
    url = f"{GH_API}/repos/{repo}/pulls/{pr_number}/files"
    files = http_json(url, headers=gh_headers(token)) or []

    return [
        {"path": f["filename"], "patch": f["patch"]}
        for f in files
        if f.get("patch")
    ]


# ========================
# REVIEW
# ========================

def process_file_review(path, patch, openai_key):
    eligible_lines = changed_right_lines_from_patch(patch)
    if not eligible_lines:
        return []

    prompt = build_review_prompt(path, patch)
    data = call_openai(prompt, openai_key)

    output_text = extract_text_from_response(data)

    if not output_text:
        return []

    try:
        obj = json.loads(output_text)
    except Exception:
        return [{
            "path": path,
            "line": eligible_lines[0],
            "side": "RIGHT",
            "body": "⚠️ AI Review executada, mas resposta não foi JSON válido."
        }]

    comments = []

    for c in obj.get("comments", [])[:3]:
        if not isinstance(c, dict):
            continue

        # linha sugerida pela IA
        line = c.get("line")

        # valida linha
        if line not in eligible_lines:
            line = eligible_lines[0]

        title = c.get("title", "Sugestão")
        comment = c.get("comment", "")
        suggestion = c.get("suggestion")

        # habilita botão suggestion apenas se:
        # - existir suggestion
        # - for apenas 1 linha
        if suggestion and "\n" not in suggestion.strip():
            body = f"""**{title}**

{comment}

```suggestion
{suggestion}
```"""
        else:
            body = f"""**{title}**

{comment}"""

        comments.append({
            "path": path,
            "line": line,
            "side": "RIGHT",
            "body": body
        })

    if not comments:
        comments.append({
            "path": path,
            "line": eligible_lines[0],
            "side": "RIGHT",
            "body": "🤖 AI Review executada com sucesso."
        })

    return comments



# ========================
# PUBLISH
# ========================

def publish_review(repo, token, pr_sha, pr_number, comments):
    if not comments:
        return

    for c in comments:
        url = f"{GH_API}/repos/{repo}/pulls/{pr_number}/comments"

        payload = {
            "body": c["body"],
            "commit_id": pr_sha,
            "path": c["path"],
            "side": "RIGHT",
            "line": c["line"]
        }

        http_json(
            url,
            method="POST",
            headers=gh_headers(token),
            body=json.dumps(payload).encode("utf-8")
        )


# ========================
# MAIN
# ========================

def main():
    repo, token, pr_sha, pr_number, openai_key = _validate_environment()

    files = fetch_pr_files(repo, token, pr_number)

    all_comments = []

    for f in files[:10]:
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
