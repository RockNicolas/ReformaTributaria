"""Conector Sienge: lê os itens das notas fiscais (API Bulk Data) e extrai os produtos (NCM) a classificar.

VERIFICADO na documentação do Sienge (ajuda.sienge.com.br): endpoint /bulk-data/v1/invoice-itens, filtros de
período (startDate/endDate), retorna NCM, CFOP, produto fiscal (código e descrição), CSTs e valores.
Só funciona para clientes Sienge em nuvem (DC).

NÃO VERIFICADO (confirmar no primeiro uso com credenciais reais): autenticação (aqui: Basic user:senha, padrão
das APIs Sienge), URL base com subdomínio, nomes exatos das chaves JSON e formato de paginação. Por isso o
extrator reconhece as chaves por nome aproximado e, se não achar o NCM, devolve as chaves recebidas para ajuste.
"""
import re
import unicodedata

import httpx


class ConectorErro(RuntimeError):
    pass


def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


class Sienge:
    def __init__(self, subdominio: str, usuario: str, senha: str, base_url: str | None = None, transport=None):
        if not (subdominio or base_url):
            raise ConectorErro("Informe o subdomínio do Sienge.")
        self.base = (base_url or f"https://api.sienge.com.br/{subdominio}/public/api").rstrip("/")
        self._c = httpx.AsyncClient(auth=(usuario, senha), timeout=60, transport=transport)

    async def itens_notas(self, inicio: str, fim: str, empresa: str | None = None, limite: int = 50000) -> list[dict]:
        params = {"startDate": inicio, "endDate": fim}
        if empresa:
            params["companyId"] = empresa
        try:
            r = await self._c.get(f"{self.base}/bulk-data/v1/invoice-itens", params=params)
        except httpx.HTTPError as e:
            raise ConectorErro(f"Sem resposta do Sienge: {e}") from e
        if r.status_code in (401, 403):
            raise ConectorErro("Sienge recusou as credenciais (HTTP %d). Confira usuário, senha e permissão de API." % r.status_code)
        if r.status_code >= 400:
            raise ConectorErro(f"Sienge respondeu HTTP {r.status_code}: {r.text[:200]}")
        dados = r.json()
        if isinstance(dados, dict):
            dados = next((dados[k] for k in ("data", "results", "items", "itens") if isinstance(dados.get(k), list)), None)
        if not isinstance(dados, list):
            raise ConectorErro("Formato de resposta do Sienge não reconhecido (esperava uma lista de itens).")
        return dados[:limite]

    async def fechar(self):
        await self._c.aclose()


def _achar_chaves(amostra: dict) -> dict:
    ks = {k: _n(k) for k in amostra}
    ncm = next((k for k, v in ks.items() if "ncm" in v), None)
    desc = (next((k for k, v in ks.items() if "descri" in v and ("fiscal" in v or "produto" in v or "product" in v)), None)
            or next((k for k, v in ks.items() if "descri" in v), None))
    cod = (next((k for k, v in ks.items() if ("produtofiscal" in v or "fiscalproduct" in v)
                 and any(t in v for t in ("codigo", "code", "id"))), None)
           or next((k for k, v in ks.items() if v in ("codigo", "code", "productcode", "codigoproduto")), None))
    return {"ncm": ncm, "descricao": desc, "codigo": cod}


def extrair_produtos(registros: list[dict]) -> list[dict]:
    """Produtos distintos (codigo, descricao, ncm) a partir dos itens de nota."""
    if not registros:
        return []
    ch = _achar_chaves(registros[0])
    if not ch["ncm"]:
        raise ConectorErro("Não encontrei o campo de NCM na resposta do Sienge. Chaves recebidas: "
                           + ", ".join(sorted(registros[0].keys())[:40]))
    vistos: dict[tuple, dict] = {}
    for r in registros:
        ncm = re.sub(r"\D", "", str(r.get(ch["ncm"]) or ""))
        desc = str(r.get(ch["descricao"]) or "").strip() if ch["descricao"] else ""
        cod = str(r.get(ch["codigo"]) or "").strip() if ch["codigo"] else ""
        chave = (cod or desc, ncm)
        if chave not in vistos:
            vistos[chave] = {"codigo": cod or f"sienge-{len(vistos) + 1}", "descricao": desc, "ncm": ncm}
    return list(vistos.values())
