"""Autenticação por X-API-Key + limite de requisições por minuto (em memória, por chave/IP)."""
import hmac
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_janelas: dict[str, deque] = defaultdict(deque)


async def exigir_acesso(request: Request):
    chave = request.headers.get("x-api-key", "")
    if config.API_KEYS:
        if not any(hmac.compare_digest(chave, k) for k in config.API_KEYS):
            raise HTTPException(401, "API key ausente ou inválida (header X-API-Key).")
        quem = "k:" + chave
    else:
        quem = "ip:" + (request.client.host if request.client else "?")
    agora = time.monotonic()
    j = _janelas[quem]
    while j and agora - j[0] > 60:
        j.popleft()
    if len(j) >= config.LIMITE_POR_MINUTO:
        raise HTTPException(429, "Limite de requisições por minuto excedido.", headers={"Retry-After": "60"})
    j.append(agora)
