
"""
Templates de prompts para AI Code Review.

Este módulo centraliza todos os templates de prompts utilizados
para comunicação com OpenAI, facilitando manutenção e auditoria.
"""


# ============================================================
# FEATURE FLAGS - Plataforma de Engenharia Assistida
# ============================================================

AI_FEATURE_FLAGS = {
    "REVIEW_ENABLED": True,
    "SUGGESTIONS_ENABLED": True,
    "REFACTOR_MODE": True,
    "LINT_MODE": False,
    "ARCHITECTURE_ANALYSIS": True,
    "FORCE_GITHUB_SUGGESTION_BUTTON": True,
    "MAX_COMMENTS_PER_FILE": 3
}


# ============================================================
# TEMPLATE BASE
# ============================================================

REVIEW_PROMPT_TEMPLATE = """Você é um revisor técnico especialista, direto e pragmático.

⚠ IMPORTANTE:
- Analise EXCLUSIVAMENTE as linhas adicionadas (lado RIGHT).
- NÃO comente linhas removidas.
- NÃO invente linhas fora do DIFF.
- O campo "line" deve conter o número exato da linha do lado RIGHT.

Sua análise deve considerar:

- Clean Architecture
- SOLID
- Clean Code
- DDD
- Separação de responsabilidades
- Baixo acoplamento e alta coesão
- Complexidade ciclomática
- Testabilidade
- Segurança
- Performance quando aplicável

Regras obrigatórias:

1. Gere no máximo {max_comments} comentários.
2. Responda SOMENTE JSON válido.
3. O JSON deve ter exatamente este formato:

{{
  "comments": [
    {{
      "line": <numero_da_linha_do_lado_RIGHT>,
      "title": "Título objetivo",
      "comment": "Comentário técnico claro e acionável"{suggestion_field}
    }}
  ]
}}

4. O campo "suggestion" é opcional.
5. Se existir suggestion, deve ser apenas o código puro (SEM markdown, SEM crases, SEM ```).
6. Nunca inclua texto fora do JSON.
7. Nunca inclua explicações fora da estrutura JSON.
8. Nunca use blocos ```suggestion``` — apenas forneça o código puro no campo suggestion.

DIFF do arquivo {path}:
{patch}
"""


def build_review_prompt(file_path, patch_content, max_patch_size=8000):
    sanitized_patch = patch_content[:max_patch_size] if patch_content else ""
    max_comments = AI_FEATURE_FLAGS.get("MAX_COMMENTS_PER_FILE", 3)
    force_button = AI_FEATURE_FLAGS.get("FORCE_GITHUB_SUGGESTION_BUTTON", False)

    if force_button:
        suggestion_field = ', "suggestion": "Código obrigatório substituindo a linha analisada"'
        suggestion_rules = """
        4. O campo "suggestion" é OBRIGATÓRIO.
        5. Sempre gere código substituindo exatamente a linha analisada.
        """
    else:
        suggestion_field = ', "suggestion": "codigo opcional em uma única linha quando possível"'
        suggestion_rules = """
        4. O campo "suggestion" é opcional.
        5. Se existir suggestion, deve ser apenas o código puro.
        """

    return REVIEW_PROMPT_TEMPLATE.format(
        path=file_path,
        patch=sanitized_patch,
        max_comments=max_comments,
        suggestion_field=suggestion_field,
        suggestion_rules=suggestion_rules
    )

