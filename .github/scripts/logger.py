"""
Sistema de logging para AI Code Review.

Fornece funções para rastreamento de operações com diferentes níveis
de severidade, melhorando observabilidade e debugging.
"""

import sys
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Níveis de log disponíveis."""
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


def _format_log_message(level, message):
    """
    Formata mensagem de log com timestamp e nível.
    
    Args:
        level: LogLevel do log
        message: Mensagem a logar
    
    Returns:
        String formatada pronta para imprimir
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] [{level.value}] {message}"


def info(message):
    """Loga mensagem informativa."""
    print(_format_log_message(LogLevel.INFO, message), file=sys.stdout)


def success(message):
    """Loga operação bem-sucedida."""
    print(_format_log_message(LogLevel.SUCCESS, message), file=sys.stdout)


def warning(message):
    """Loga aviso/alerta."""
    print(_format_log_message(LogLevel.WARNING, message), file=sys.stderr)


def error(message):
    """Loga erro."""
    print(_format_log_message(LogLevel.ERROR, message), file=sys.stderr)


def debug(message):
    """Loga mensagem de debug."""
    print(_format_log_message(LogLevel.DEBUG, message), file=sys.stdout)


def operation_start(operation_name):
    """Loga início de operação."""
    info(f"Iniciando: {operation_name}")


def operation_success(operation_name, details=""):
    """Loga sucesso de operação."""
    msg = f"✓ {operation_name}"
    if details:
        msg += f" - {details}"
    success(msg)


def operation_failed(operation_name, reason=""):
    """Loga falha de operação."""
    msg = f"✗ {operation_name}"
    if reason:
        msg += f" - {reason}"
    error(msg)


def operation_skipped(operation_name, reason=""):
    """Loga operação pulada."""
    msg = f"⊘ {operation_name} (pulada)"
    if reason:
        msg += f" - {reason}"
    warning(msg)


def summary(total, success_count, skipped_count, failed_count):
    """Loga resumo final de operações."""
    info(f"Resumo: {success_count} sucesso, {skipped_count} pulada, {failed_count} falha (total: {total})")
