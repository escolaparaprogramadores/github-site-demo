# Standard library imports
import json
import os
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Local imports
from prompt_templates import build_review_prompt
from logger import (
    info, success, warning, error, debug,
    operation_start, operation_success, operation_failed, operation_skipped,
    summary
)


def _validate_environment():
    """
    Valida variáveis de ambiente obrigatórias de forma segura.
    Evita expor quais configurações estão faltando.
    
    Returns:
        tuple: (repo, gh_token, pr_sha, pr_number, openai_key) ou sai com erro genérico
    
    Raises:
        SystemExit: Se alguma variável obrigatória está faltando
    """
    operation_start("Validação de ambiente")
    
    repo = (os.environ.get("REPO") or "").strip()
    gh_token = (os.environ.get("GH_TOKEN") or "").strip()
    pr_sha = (os.environ.get("PR_SHA") or "").strip()
    pr_number_raw = (os.environ.get("PR_NUMBER") or "").strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    
    # Validação de requisitos mínimos - sem expor detalhes
    required_vars = [
        ("REPO", repo),
        ("GH_TOKEN", gh_token),
        ("PR_SHA", pr_sha),
        ("OPENAI_API_KEY", openai_key),
        ("PR_NUMBER", pr_number_raw)
    ]
    
    missing = [name for name, value in required_vars if not value]
    
    if missing:
        operation_failed("Validação de ambiente", "Configuração ausente")
        print("Erro: Configuração ausente. Encerrando.")
        raise SystemExit(1)
    
    # Validar formato do PR_NUMBER
    if not pr_number_raw.isdigit():
        operation_failed("Validação de ambiente", "Configuração inválida")
        print("Erro: Configuração inválida. Encerrando.")
        raise SystemExit(1)
    
    pr_number = int(pr_number_raw)
    operation_success("Validação de ambiente", f"PR #{pr_number}")
    
    return repo, gh_token, pr_sha, pr_number, openai_key


# Validar e carregar variáveis de ambiente
try:
    REPO, GH_TOKEN, PR_SHA, PR_NUMBER, OPENAI_API_KEY = _validate_environment()
except SystemExit:
    raise

GH_API = "https://api.github.com"
OAI_API = "https://api.openai.com/v1/chat/completions"

def _calculate_retry_wait(attempt, retry_after_header=None):
    """Calcula tempo de espera para retry com backoff exponencial."""
    if retry_after_header:
        try:
            return min(int(retry_after_header), 60)
        except (ValueError, TypeError):
            pass
    return min((2 ** attempt) + random.uniform(0, 2), 60)


def _should_retry_http_error(status_code):
    """Determina se deve fazer retry para um código HTTP específico."""
    return status_code in (429, 500, 502, 503, 504)


def _handle_http_error(error, url, attempt, max_attempts):
    """Trata erro HTTP e retorna True se deve fazer retry."""
    if not _should_retry_http_error(error.code):
        # Não logar corpo de erro sensível (pode conter info de configuração)
        _log_error_safe(f"HTTP {error.code}: Erro não recuperável", is_sensitive=True)
        raise
    
    retry_after = error.headers.get("Retry-After")
    wait = _calculate_retry_wait(attempt, retry_after)
    print(f"Tentativa {attempt}/{max_attempts} em {wait:.1f}s")
    time.sleep(wait)
    return True


def _handle_url_error(error, url, attempt, max_attempts):
    """Trata erro de rede e faz retry."""
    wait = _calculate_retry_wait(attempt)
    # Não expor URL completa por segurança (pode conter informações sensíveis)
    print(f"Tentativa {attempt}/{max_attempts} em {wait:.1f}s")
    time.sleep(wait)
    return True


def http_json(url, method="GET", headers=None, body=None, max_attempts=6):
    """Realiza requisição HTTP e retorna JSON, com retry automático."""
    headers = headers or {}
    last_err = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            req = Request(url, method=method, headers=headers, data=body)
            with urlopen(req, timeout=60) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data) if data else None
        except HTTPError as e:
            last_err = e
            if not _handle_http_error(e, url, attempt, max_attempts):
                raise
        except URLError as e:
            last_err = e
            _handle_url_error(e, url, attempt, max_attempts)
    
    _log_error_safe("Requisição HTTP falhou após retentativas", is_sensitive=True)
    raise RuntimeError("Request failed after retries")

def gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-code-review-bot"
    }


def verify_pr_access():
    """
    Verifica se o token GH tem permissão de acesso ao PR.
    
    Returns:
        bool: True se há acesso ao PR, False caso contrário
    
    Raises:
        SystemExit: Se não há acesso
    """
    operation_start(f"Verificação de acesso ao PR #{PR_NUMBER}")
    
    try:
        url = f"{GH_API}/repos/{REPO}/pulls/{PR_NUMBER}"
        http_json(url, headers=gh_headers())
        operation_success(f"Acesso ao PR", f"Repositório: {REPO}")
        return True
    except HTTPError as e:
        if e.code == 401:
            operation_failed("Verificação de acesso", "Token inválido ou expirado")
            _log_error_safe("Token inválido ou expirado", is_sensitive=True)
        elif e.code == 403:
            operation_failed("Verificação de acesso", "Sem permissão")
            _log_error_safe("Sem permissão para acessar o PR", is_sensitive=True)
        elif e.code == 404:
            operation_failed("Verificação de acesso", "PR não encontrado")
            _log_error_safe("PR não encontrado", is_sensitive=True)
        else:
            operation_failed("Verificação de acesso", f"Erro HTTP {e.code}")
            _log_error_safe(f"Erro ao verificar acesso", is_sensitive=True)
        raise SystemExit(1)
    except Exception as e:
        operation_failed("Verificação de acesso", "Falha de conexão")
        _log_error_safe("Falha ao verificar acesso ao repositório", is_sensitive=True)
        raise SystemExit(1)

def oai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }


def _log_error_safe(error_msg, is_sensitive=False):
    """
    Log seguro que evita expor informações sensíveis.
    
    Args:
        error_msg: Mensagem a logar
        is_sensitive: Se True, não loga em detalhes
    """
    if is_sensitive:
        print("Erro: Falha ao comunicar com serviço externo")
    else:
        print(error_msg)

def post_issue_comment(msg: str):
    """Publica comentário na PR de forma segura."""
    url = f"{GH_API}/repos/{REPO}/issues/{PR_NUMBER}/comments"
    try:
        http_json(url, method="POST", headers=gh_headers(), body=json.dumps({"body": msg}).encode("utf-8"))
    except Exception as e:
        _log_error_safe(f"Falha ao postar comentário: {e}", is_sensitive=True)

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
    """Chama OpenAI API e retorna resposta JSON, com retry automático."""
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            req = Request(OAI_API, headers=oai_headers(), data=body)
            with urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            last_err = e
            if not _handle_http_error(e, OAI_API, attempt, max_attempts):
                raise
        except URLError as e:
            last_err = e
            _handle_url_error(e, OAI_API, attempt, max_attempts)
    
    _log_error_safe("OpenAI API falhou após retentativas", is_sensitive=True)
    raise RuntimeError("OpenAI failed after retries")


def fetch_pr_files():
    """
    Busca todos os arquivos modificados do PR com paginação.
    
    Returns:
        list: Lista de dicts com {path, patch} dos arquivos
    """
    operation_start("Busca de arquivos modificados")
    
    files = []
    page = 1
    
    while True:
        url = f"{GH_API}/repos/{REPO}/pulls/{PR_NUMBER}/files?per_page=100&page={page}"
        chunk = http_json(url, headers=gh_headers())
        if not chunk:
            break
        files.extend(chunk)
        debug(f"Página {page}: {len(chunk)} arquivos carregados")
        if len(chunk) < 100:
            break
        page += 1
    
    selected = []
    for f in files:
        filename = f.get("filename")
        patch = f.get("patch")
        if filename and patch:
            selected.append({"path": filename, "patch": patch})
    
    operation_success("Busca de arquivos", f"{len(selected)} arquivo(s) com diffs textuais")
    
    return selected


def process_file_review(path, patch):
    """
    Processa review de um arquivo individual com OpenAI.
    
    Args:
        path: Caminho do arquivo
        patch: Diff/patch do arquivo
    
    Returns:
        list: Lista de comentários {"path", "line", "side", "body"}
    """
    eligible_lines = sorted(list(changed_right_lines_from_patch(patch)))
    if not eligible_lines:
        operation_skipped(path, "Sem linhas modificadas")
        return []

    debug(f"Processando {path}: {len(eligible_lines)} linha(s) modificada(s)")

    prompt = build_review_prompt(path, patch)

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Você é um revisor técnico sênior. Responda somente JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 450
    }

    try:
        data = call_openai(payload)
    except Exception as e:
        operation_failed(f"Review: {path}", "Falha na OpenAI API")
        return []

    content = (data["choices"][0]["message"]["content"] or "").strip()
    if not content:
        operation_skipped(path, "Resposta vazia da OpenAI")
        return []

    try:
        obj = json.loads(content)
    except Exception:
        warning(f"Falha ao parsear JSON para {path}")
        return []

    comments = obj.get("comments", []) or []
    eligible_set = set(eligible_lines)
    file_comments = []

    for c in comments[:3]:
        line = c.get("line")
        body = c.get("body")
        if not isinstance(line, int) or not body:
            continue
        if line not in eligible_set:
            line = min(eligible_lines, key=lambda x: abs(x - line))
        file_comments.append({"path": path, "line": line, "side": "RIGHT", "body": body[:900]})

    if file_comments:
        operation_success(f"Review: {path}", f"{len(file_comments)} comentário(s)")
    else:
        operation_skipped(path, "Sem comentários relevantes")

    return file_comments


def generate_reviews(files):
    """
    Gera reviews para múltiplos arquivos.
    
    Args:
        files: Lista de {path, patch}
    
    Returns:
        list: Todos os comentários inline
    """
    operation_start(f"Geração de reviews: {len(files)} arquivo(s)")
    
    all_comments = []
    processed = 0
    
    for item in files[:12]:
        path = item["path"]
        patch = item["patch"]
        comments = process_file_review(path, patch)
        all_comments.extend(comments)
        processed += 1
    
    trimmed = all_comments[:12]
    operation_success("Geração de reviews", f"{len(trimmed)} comentário(s) total")
    
    return trimmed


def publish_review(comments):
    """
    Publica review no PR com comentários inline.
    
    Args:
        comments: Lista de comentários a publicar
    
    Raises:
        SystemExit: Se não houver comentários para publicar
    """
    if not comments:
        operation_skipped("Publicação", "Nenhum comentário para publicar")
        post_issue_comment("## 🤖 AI Code Review\n\nSem comentários inline relevantes neste diff. ✅")
        raise SystemExit(0)

    operation_start(f"Publicação de review: {len(comments)} comentário(s)")

    summary_text = "## 🤖 AI Code Review\n\n- Comentários inline adicionados nos arquivos alterados."

    review_payload = {
        "commit_id": PR_SHA,
        "body": summary_text,
        "event": "COMMENT",
        "comments": comments
    }

    try:
        url = f"{GH_API}/repos/{REPO}/pulls/{PR_NUMBER}/reviews"
        resp = http_json(url, method="POST", headers=gh_headers(), body=json.dumps(review_payload).encode("utf-8"))
        review_url = (resp or {}).get("html_url")
        if review_url:
            operation_success("Publicação de review", review_url)
        else:
            operation_success("Publicação de review", "Review criado")
    except Exception as e:
        operation_failed("Publicação de review", str(e))
        raise SystemExit(1)


# ===== MAIN EXECUTION FLOW =====

info("=" * 60)
info("Iniciando AI Code Review")
info("=" * 60)

# 1) Verificar acesso ao PR com token
try:
    verify_pr_access()
except SystemExit:
    raise

# 2) Buscar arquivos do PR
try:
    files = fetch_pr_files()
except Exception as e:
    operation_failed("Busca de arquivos", str(e))
    raise SystemExit(1)

if not files:
    operation_skipped("Processamento", "Nenhum arquivo com diffs textuais")
    post_issue_comment("## 🤖 AI Code Review\n\nSem patch textual para revisar. ✅")
    raise SystemExit(0)

# 3) Gerar reviews para os arquivos
try:
    comments = generate_reviews(files)
except Exception as e:
    operation_failed("Geração de reviews", str(e))
    raise SystemExit(1)

# 4) Publicar review
try:
    publish_review(comments)
except SystemExit as e:
    if e.code == 0:
        raise
    error("Falha ao publicar review")
    raise

info("=" * 60)
success("AI Code Review concluído com sucesso!")
info("=" * 60)
