import os, json, time, random, re
import urllib.request
from urllib.error import HTTPError, URLError

REPO = (os.environ.get("REPO") or "").strip()
PR_NUMBER_RAW = (os.environ.get("PR_NUMBER") or "").strip()
PR_SHA = (os.environ.get("PR_SHA") or "").strip()
GH_TOKEN = (os.environ.get("GH_TOKEN") or "").strip()
OPENAI_API_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()

if not REPO or not GH_TOKEN or not PR_SHA:
    print("REPO/GH_TOKEN/PR_SHA ausente. Encerrando.")
    raise SystemExit(0)

if not OPENAI_API_KEY:
    print("OPENAI_API_KEY vazio. Encerrando sem review.")
    raise SystemExit(0)

if not PR_NUMBER_RAW.isdigit():
    print(f"PR_NUMBER inválido/vazio: '{PR_NUMBER_RAW}'. Encerrando sem review.")
    raise SystemExit(0)

PR_NUMBER = int(PR_NUMBER_RAW)

GH_API = "https://api.github.com"
OAI_API = "https://api.openai.com/v1/chat/completions"

def http_json(url, method="GET", headers=None, body=None, max_attempts=6):
    headers = headers or {}
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, method=method, headers=headers, data=body)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data) if data else None
        except HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After")
                wait = min(int(ra), 60) if ra else min((2 ** attempt) + random.uniform(0, 2), 60)
                print(f"HTTP {e.code} on {url}. Retry {attempt}/{max_attempts} in {wait:.1f}s")
                time.sleep(wait)
                continue
            try:
                msg = e.read().decode("utf-8")
                print("HTTPError body:", msg[:800])
            except Exception:
                pass
            raise
        except URLError as e:
            last_err = e
            wait = min((2 ** attempt) + random.uniform(0, 2), 60)
            print(f"Network error on {url}: {e}. Retry {attempt}/{max_attempts} in {wait:.1f}s")
            time.sleep(wait)
            continue
    raise RuntimeError(f"Request failed after retries: {last_err}")

def gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-code-review-bot"
    }

def oai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

def post_issue_comment(msg: str):
    url = f"{GH_API}/repos/{REPO}/issues/{PR_NUMBER}/comments"
    http_json(url, method="POST", headers=gh_headers(), body=json.dumps({"body": msg}).encode("utf-8"))

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

def call_openai(payload, max_attempts=6):
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(OAI_API, headers=oai_headers(), data=body)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                ra = e.headers.get("Retry-After")
                wait = min(int(ra), 60) if ra else min((2 ** attempt) + random.uniform(0, 2), 60)
                print(f"OpenAI HTTP {e.code}. Retry {attempt}/{max_attempts} in {wait:.1f}s")
                time.sleep(wait)
                continue
            try:
                msg = e.read().decode("utf-8")
                print("OpenAI HTTPError body:", msg[:800])
            except Exception:
                pass
            raise
        except URLError as e:
            last_err = e
            wait = min((2 ** attempt) + random.uniform(0, 2), 60)
            print(f"OpenAI network error: {e}. Retry {attempt}/{max_attempts} in {wait:.1f}s")
            time.sleep(wait)
            continue
    raise RuntimeError(f"OpenAI failed after retries: {last_err}")

# Lista arquivos do PR
files = []
page = 1
while True:
    url = f"{GH_API}/repos/{REPO}/pulls/{PR_NUMBER}/files?per_page=100&page={page}"
    chunk = http_json(url, headers=gh_headers())
    if not chunk:
        break
    files.extend(chunk)
    if len(chunk) < 100:
        break
    page += 1

selected = []
for f in files:
    filename = f.get("filename")
    patch = f.get("patch")
    if filename and patch:
        selected.append({"path": filename, "patch": patch})

if not selected:
    post_issue_comment("## 🤖 AI Code Review\n\nSem patch textual para revisar. ✅")
    raise SystemExit(0)

per_file_comments = []

for item in selected[:12]:
    path = item["path"]
    patch = item["patch"]
    eligible_lines = sorted(list(changed_right_lines_from_patch(patch)))
    if not eligible_lines:
        continue

    patch_for_prompt = patch[:8000]

    prompt = f"""
Você é um revisor técnico especialista, direto e pragmático.

Analise exclusivamente as linhas adicionadas (RIGHT side) do diff.
NÃO comente linhas removidas.
NÃO invente linhas fora do DIFF.
Comente apenas linhas que realmente aparecem no lado RIGHT.

Sua análise deve considerar profundamente:

- Clean Architecture
- SOLID
- Clean Code
- DDD (Domain-Driven Design)
- Entidades e agregados
- Separação de responsabilidades
- Baixo acoplamento e alta coesão
- Complexidade ciclomática
- Legibilidade e manutenibilidade
- Produtividade do código
- Testabilidade (TDD)
- Boas práticas da linguagem utilizada
- Segurança e riscos técnicos
- Performance quando aplicável

Regras obrigatórias:

1. Gere no máximo 3 comentários por arquivo.
2. Cada comentário deve começar com um TÍTULO em português indicando o tipo da observação.
3. Se for algo opcional/melhoria não obrigatória, comece o título com:
   "Sugestão:"
4. Se houver violação clara de princípios (SOLID, Clean Architecture, etc), use um título direto como:
   - "Violação de SRP"
   - "Problema de Acoplamento"
   - "Complexidade Excessiva"
   - "Risco Arquitetural"
   - "Quebra de Clean Architecture"
   - etc.
5. Seja específico e acionável.
6. Não escreva textos genéricos.
7. Seja objetivo e técnico.
8. Responda SOMENTE JSON válido.

Formato obrigatório de resposta:


IMPORTANTE:
- O campo "line" deve ser o número da linha do lado RIGHT do DIFF.
- Não inclua explicações fora do JSON.
- Não inclua markdown.
- Não inclua texto adicional.
- Apenas JSON válido.


{{"comments":[{{"path":"{path}","line":123,"body": "Título: descrição objetiva e acionável (1-4 linhas no máximo)"}}]}}

DIFF:
{patch_for_prompt}
"""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Você é um revisor técnico sênior. Responda somente JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 450
    }

    data = call_openai(payload)
    content = (data["choices"][0]["message"]["content"] or "").strip()
    if not content:
        continue

    try:
        obj = json.loads(content)
    except Exception:
        continue

    comments = obj.get("comments", []) or []
    eligible_set = set(eligible_lines)

    for c in comments[:3]:
        line = c.get("line")
        body = c.get("body")
        if not isinstance(line, int) or not body:
            continue
        if line not in eligible_set:
            line = min(eligible_lines, key=lambda x: abs(x - line))
        per_file_comments.append({"path": path, "line": line, "side": "RIGHT", "body": body[:900]})

if not per_file_comments:
    post_issue_comment("## 🤖 AI Code Review\n\nSem comentários inline relevantes neste diff. ✅")
    raise SystemExit(0)

summary = "## 🤖 AI Code Review\n\n- Comentários inline adicionados nos arquivos alterados."

review_payload = {
    "commit_id": PR_SHA,
    "body": summary,
    "event": "COMMENT",
    "comments": per_file_comments[:12]
}

url = f"{GH_API}/repos/{REPO}/pulls/{PR_NUMBER}/reviews"
resp = http_json(url, method="POST", headers=gh_headers(), body=json.dumps(review_payload).encode("utf-8"))
print("Review created:", (resp or {}).get("html_url"))
