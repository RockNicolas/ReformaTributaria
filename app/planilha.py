"""Planilha de produtos -> planilha de cadastro fiscal pronta para importar no ERP.

Entrada: CSV (separador ; ou ,) com colunas de código, descrição e NCM (nomes flexíveis).
Para cada NCM: sugere CST + cClassTrib (vinculados por lei ou padrão) e CONFERE o par no motor oficial.
"""
import asyncio
import csv
import hashlib
import io
import re
import unicodedata

from . import config
from .calculadora import Calculadora, CalculadoraErro
from .sugestao import sugerir
from .ufs import CAPITAIS
from .sugestoes import sugestao_para

SAIDA = ["codigo", "descricao", "ncm", "cst", "cclasstrib", "descricao_classificacao",
         "status", "validacao_motor", "problema", "o_que_fazer"]
_ALIAS = {
    "codigo": {"codigo", "cod", "cprod", "sku", "referencia", "ref", "id"},
    "descricao": {"descricao", "produto", "nome", "xprod", "item", "mercadoria"},
    "ncm": {"ncm", "codigoncm", "ncmsh", "classificacaofiscal"},
}


class PlanilhaInvalida(ValueError):
    pass


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def ler_csv(conteudo: bytes) -> list[dict]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")
    amostra = texto[:2000]
    delim = ";" if amostra.count(";") >= amostra.count(",") else ","
    leitor = csv.reader(io.StringIO(texto), delimiter=delim)
    linhas = [l for l in leitor if any(c.strip() for c in l)]
    if len(linhas) < 2:
        raise PlanilhaInvalida("A planilha precisa de um cabeçalho e ao menos uma linha de produto.")
    cab = [_norm(c) for c in linhas[0]]
    idx = {}
    for campo, nomes in _ALIAS.items():
        for i, c in enumerate(cab):
            if c in nomes and campo not in idx:
                idx[campo] = i
    if "ncm" not in idx:
        raise PlanilhaInvalida("Não encontrei a coluna de NCM. Use um cabeçalho como: codigo;descricao;ncm")
    if len(linhas) - 1 > 20000:
        raise PlanilhaInvalida("Máximo de 20.000 produtos por planilha.")
    out = []
    for n, l in enumerate(linhas[1:], start=1):
        def g(campo):
            i = idx.get(campo)
            return l[i].strip() if i is not None and i < len(l) else ""
        out.append({"codigo": g("codigo") or f"linha-{n}", "descricao": g("descricao"),
                    "ncm": re.sub(r"\D", "", g("ncm"))})
    return out


async def processar(calc: Calculadora, produtos: list[dict], uf: str, municipio: int, data: str) -> list[dict]:
    municipio = municipio or CAPITAIS.get(uf.upper(), 3550308)
    validos = {p["ncm"] for p in produtos if len(p["ncm"]) == 8}
    sug = {s["ncm"]: s for s in await sugerir(
        calc, [{"ncm": n, "produto": ""} for n in sorted(validos)], data)}
    linhas = []
    for p in produtos:
        base = {"codigo": p["codigo"], "descricao": p["descricao"], "ncm": p["ncm"], "cst": "",
                "cclasstrib": "", "descricao_classificacao": "", "status": "", "validacao_motor": "",
                "problema": "", "o_que_fazer": ""}
        if len(p["ncm"]) != 8:
            base.update(status="SEM_NCM", problema="NCM ausente ou incompleto (precisa de 8 dígitos).",
                        o_que_fazer="Completar o NCM no cadastro. Se for serviço, use NBS (fora desta planilha).")
        else:
            s = sug.get(p["ncm"], {})
            base.update(cst=s.get("cst_sugerido", ""), cclasstrib=s.get("cclasstrib_sugerido", ""),
                        descricao_classificacao=s.get("descricao_sugerida", ""), status=s.get("status", "INDETERMINADO"))
            if not base["cst"]:
                base.update(problema=s.get("observacao", "Sem sugestão."), o_que_fazer="Definir a classificação manualmente com o contador.")
        linhas.append(base)

    # Conferência no motor: o par sugerido precisa ser aceito para o NCM/UF/data.
    conferir = [(i, l) for i, l in enumerate(linhas) if l["cst"]]
    sem = asyncio.Semaphore(4)

    async def lote(pedaco):
        op = {"id": hashlib.md5(f"{data}{pedaco[0][0]}".encode()).hexdigest(), "versao": "1.0.0",
              "dhFatoGerador": data, "municipio": municipio, "uf": uf, "tpDoc": 55,
              "itens": [{"numero": k + 1, "ncm": l["ncm"], "cst": l["cst"], "cClassTrib": l["cclasstrib"],
                         "baseCalculo": 100.0,
                         **({"aliquotasNominais": {"cbs": config.ALIQ_CBS, "ibsEstadual": config.ALIQ_IBS_UF,
                                                   "ibsMunicipal": config.ALIQ_IBS_MUN}} if data[:4] >= "2027" else {})}
                        for k, (_, l) in enumerate(pedaco)]}
        try:
            async with sem:
                resp = await calc.observabilidade(op)
        except CalculadoraErro as e:
            for _, l in pedaco:
                l["validacao_motor"] = "NAO_VERIFICADO"
                l["problema"] = f"Motor indisponível: {e}"
            return
        for obj in resp.get("objetos", []):
            k = obj.get("nObj", 0) - 1
            if not 0 <= k < len(pedaco):
                continue
            l = pedaco[k][1]
            if obj.get("estadoItem") in ("CALCULADO", "CALCULO_SIMULADO"):
                l["validacao_motor"] = "OK"
                l["o_que_fazer"] = ("Importar no ERP." if l["status"] == "PADRAO_PROVAVEL"
                                    else "Conferir com o contador (NCM com tratamento específico) e importar.")
            else:
                e0 = (obj.get("erros") or [{}])[0]
                l["validacao_motor"] = "ERRO"
                l["problema"] = f"{e0.get('code', '')} {e0.get('title', '')}".strip()
                l["o_que_fazer"] = sugestao_para(e0.get("code", ""))

    await asyncio.gather(*(lote(conferir[i:i + 100]) for i in range(0, len(conferir), 100)))
    return linhas


def para_csv(linhas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=SAIDA, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerows(linhas)
    return "﻿" + buf.getvalue()


def resumo(linhas: list[dict]) -> dict:
    c = lambda f: sum(1 for l in linhas if f(l))
    return {"total": len(linhas), "prontos": c(lambda l: l["validacao_motor"] == "OK" and l["status"] == "PADRAO_PROVAVEL"),
            "revisar": c(lambda l: l["validacao_motor"] == "OK" and l["status"] == "REVISAR"),
            "com_erro": c(lambda l: l["validacao_motor"] in ("ERRO", "NAO_VERIFICADO")),
            "sem_ncm": c(lambda l: l["status"] == "SEM_NCM")}
