"""Conector Omie: lista os produtos (código, descrição, NCM) pela API do Omie ERP.

Verificado na ajuda do Omie: POST https://app.omie.com.br/api/v1/geral/produtos/ com
{"call": "ListarProdutos", "app_key", "app_secret", "param": [{pagina, registros_por_pagina, apenas_importado_api,
filtrar_apenas_omiepdv}]}; o produto tem os campos codigo, descricao e ncm.
Não verificado: nome da chave da lista na resposta e do total de páginas (o código procura a lista sozinho).
"""
import httpx

from .sienge import ConectorErro

URL = "https://app.omie.com.br/api/v1/geral/produtos/"


async def listar_produtos(app_key: str, app_secret: str, transport=None, max_paginas: int = 200) -> list[dict]:
    produtos, pagina, total = [], 1, 1
    async with httpx.AsyncClient(timeout=60, transport=transport) as c:
        while pagina <= min(total, max_paginas):
            corpo = {"call": "ListarProdutos", "app_key": app_key, "app_secret": app_secret,
                     "param": [{"pagina": pagina, "registros_por_pagina": 100,
                                "apenas_importado_api": "N", "filtrar_apenas_omiepdv": "N"}]}
            try:
                r = await c.post(URL, json=corpo)
            except httpx.HTTPError as e:
                raise ConectorErro(f"Sem resposta do Omie: {e}") from e
            d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400 or "faultstring" in d:
                raise ConectorErro(f"Omie recusou a consulta: {d.get('faultstring') or r.text[:200]}")
            lista = next((v for v in d.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
            for p in lista:
                produtos.append({"codigo": str(p.get("codigo", "")).strip(),
                                 "descricao": str(p.get("descricao", "")).strip(),
                                 "ncm": "".join(ch for ch in str(p.get("ncm", "")) if ch.isdigit())})
            total = int(d.get("total_de_paginas", pagina) or pagina)
            pagina += 1
    return produtos
