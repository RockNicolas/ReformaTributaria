"""Configuração por variáveis de ambiente."""
import os


def _lista(nome: str) -> set[str]:
    return {x.strip() for x in os.getenv(nome, "").split(",") if x.strip()}


CALCULADORA_URL = os.getenv("CALCULADORA_URL", "http://localhost:8080/api")
MODO_CALCULADORA = os.getenv("MODO_CALCULADORA", "oficial")  # "oficial" | "mock"
TIMEOUT_S = float(os.getenv("CALCULADORA_TIMEOUT_S", "30"))
# Chaves de API aceitas (X-API-Key). Vazio = sem autenticação (apenas desenvolvimento).
API_KEYS = _lista("API_KEYS")
LIMITE_POR_MINUTO = int(os.getenv("LIMITE_POR_MINUTO", "60"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

# Alíquotas de SIMULAÇÃO (exemplo da documentação da Receita; não são alíquotas de cobrança).
ALIQ_CBS = float(os.getenv("ALIQ_CBS", "8.8"))
ALIQ_IBS_UF = float(os.getenv("ALIQ_IBS_UF", "0.05"))
ALIQ_IBS_MUN = float(os.getenv("ALIQ_IBS_MUN", "0.05"))
DATA_SIMULACAO = os.getenv("DATA_SIMULACAO", "2027-03-10T10:00:00-03:00")
TOLERANCIA = float(os.getenv("TOLERANCIA_CONFERENCIA", "0.02"))
