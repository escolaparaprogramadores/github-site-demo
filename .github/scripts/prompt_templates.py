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
    "MAX_COMMENTS_PER_FILE": 3
}


# ============================================================
# TEMPLATE BASE ORIGINAL (PRESERVADO)
# ============================================================

REVIEW_PROMPT_TEMPLATE = """Você é um revisor técnico especialista, direto e pragmático.

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

1. Gere no máximo {max_comments} comentários por arquivo.
2. Cada comentário deve começar com um TÍTULO em português indicando o tipo da observação.
3. Se for algo opcional/melhoria não obrigatória, comece o título com: "Sugestão:"
4. Se houver violação clara de princípios (SOLID, Clean Architecture, etc), use um título direto.
5. Seja específico e acionável.
6. Não escreva textos genéricos.
7. Seja objetivo e técnico.
8. Responda SOMENTE JSON válido.
9. Se houver possibilidade clara de correção simples, inclua bloco de sugestão aplicável no formato exato:

```suggestion
código corrigido aqui
```


DIFF do arquivo {path}:
{patch}"""


def build_review_prompt(file_path, patch_content, max_patch_size=8000):
    """
    Constrói prompt de revisão de forma segura usando template.
    
    Args:
        file_path: Caminho do arquivo sendo revisado
        patch_content: Conteúdo do patch/diff
        max_patch_size: Tamanho máximo do patch em caracteres
    
    Returns:
        String com o prompt pronto para enviar à OpenAI
    """
    sanitized_patch = patch_content[:max_patch_size] if patch_content else ""
    max_comments = AI_FEATURE_FLAGS.get("MAX_COMMENTS_PER_FILE", 3)
    
    return REVIEW_PROMPT_TEMPLATE.format(
        path=file_path,
        patch=sanitized_patch,
        max_comments=max_comments
    )