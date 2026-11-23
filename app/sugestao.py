"""Sugestão de cadastro: para cada NCM, quais classificações (CST + cClassTrib) o motor aceita.

O motor NÃO decide qual classificação o produto tem: isso é decisão fiscal. Aqui mostramos
as candidatas vinculadas ao NCM (anexo da lei) e o padrão; quando houver candidata específica,
o status é REVISAR (um contador escolhe); sem vínculo específico, PADRAO_PROVAVEL.
"""
import asyncio
import csv
import io
from datetime import date

from .calculadora import Calculadora, CalculadoraErro

PADRAO = ("000", "000001")  # tributação integral; precisa existir na base para ser sugerido
COLUNAS = ["ncm", "produto_exemplo", "status", "cst_sugerido", "cclasstrib_sugerido",
           "descricao_sugerida", "alternativas", "observacao"]


async def _catalogo(calc: Calculadora, data: str) -> dict[str, dict]:
    """cClassTrib -> {cst, descricao, nomenclatura}"""
    try:
        csts = await calc.dados_abertos("situacoes-tributarias/cbs-ibs", siglaDfe="NFe", data=data)
    except CalculadoraErro:
        csts = await calc.dados_abertos("situacoes-tributarias/cbs-ibs", data=data)
    cat: dict[str, dict] = {}
    for cst in csts:
        for c in cst.get("classificacoesTributarias") or []:
            cat[c["codigo"]] = {"cst": cst["codigo"], "descricao": c.get("descricao", ""), "nomenclatura": None}
    sem = asyncio.Semaphore(8)

    async def nomen(cod: str):
        async with sem:
            try:
                r = await calc.dados_abertos(f"nomenclatura/NFe/{cod}", data=data)
                cat[cod]["nomenclatura"] = r.get("nomenclatura")
            except CalculadoraErro:
                cat[cod]["nomenclatura"] = None

    await asyncio.gather(*(nomen(c) for c in cat))
    return cat


async def sugerir(calc: Calculadora, itens: list[dict], data: str | None = None) -> list[dict]:
    """itens: [{"ncm": "...", "produto": "..."}]. Devolve uma linha por NCM distinto."""
    data = data or date.today().isoformat()
    if data < "2026-01-01":
        data = "2026-01-01"
    ncms: dict[str, str] = {}
    for i in itens:
        if i.get("ncm"):
            ncms.setdefault(i["ncm"], i.get("produto", ""))
    if not ncms:
        return []
    cat = await _catalogo(calc, data)
    especificas = [c for c, v in cat.items() if v["nomenclatura"] in ("NCM", "MISTO", "EXCECAO_NCM")]
    sem = asyncio.Semaphore(8)

    async def vinculada(ncm: str, cod: str):
        async with sem:
            r = await calc.dados_abertos("classificacoes-tributarias/ncm-aplicavel",
                                         cClassTrib=cod, ncm=ncm, dataOcorrenciaFatoGerador=data)
            return bool(r.get("valido"))

    async def por_ncm(ncm: str, produto: str) -> dict:
        try:
            ok = await asyncio.gather(*(vinculada(ncm, c) for c in especificas))
        except CalculadoraErro as e:
            return dict(ncm=ncm, produto_exemplo=produto, status="INDETERMINADO", cst_sugerido="",
                        cclasstrib_sugerido="", descricao_sugerida="", alternativas="",
                        observacao=f"Não foi possível consultar o motor: {e}")
        cand = [c for c, v in zip(especificas, ok) if v]
        if cand:
            p = cat[cand[0]]
            return dict(ncm=ncm, produto_exemplo=produto, status="REVISAR", cst_sugerido=p["cst"],
                        cclasstrib_sugerido=cand[0], descricao_sugerida=p["descricao"],
                        alternativas="; ".join(f"{cat[c]['cst']}/{c} {cat[c]['descricao']}" for c in cand[1:]),
                        observacao="NCM vinculado a classificação específica na lei. Confirmar com o contador.")
        if PADRAO[1] in cat:
            return dict(ncm=ncm, produto_exemplo=produto, status="PADRAO_PROVAVEL", cst_sugerido=PADRAO[0],
                        cclasstrib_sugerido=PADRAO[1], descricao_sugerida=cat[PADRAO[1]]["descricao"],
                        alternativas="", observacao="Sem vínculo específico para este NCM; padrão. "
                        "Confirmar se a operação não tem outro tratamento (isenção, suspensão etc.).")
        return dict(ncm=ncm, produto_exemplo=produto, status="INDETERMINADO", cst_sugerido="",
                    cclasstrib_sugerido="", descricao_sugerida="", alternativas="",
                    observacao="Classificação padrão não encontrada na base.")

    return await asyncio.gather(*(por_ncm(n, p) for n, p in ncms.items()))


def para_csv(linhas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUNAS, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerows(linhas)
    return "﻿" + buf.getvalue()  # BOM: Excel abre com acentos corretos
