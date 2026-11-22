"""Motor: NF-e -> operação -> calculadora -> totais, pendências e divergências.

Modos:
- simulacao: projeta a carga IBS/CBS numa data futura com alíquotas de simulação.
- conferencia: recalcula na data da própria nota e compara com o IBS/CBS declarado (DIV-001).
"""
import asyncio
import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from . import config
from .calculadora import Calculadora, CalculadoraErro
from .modelos import Item, Nfe
from .sugestoes import sugestao_para

D2 = Decimal("0.01")


def r2(x) -> float:
    return float(Decimal(str(x)).quantize(D2))


@dataclass
class Opcoes:
    modo: str = "simulacao"
    data_simulacao: str = config.DATA_SIMULACAO
    aliquotas: dict = field(default_factory=lambda: {
        "cbs": config.ALIQ_CBS, "ibsEstadual": config.ALIQ_IBS_UF, "ibsMunicipal": config.ALIQ_IBS_MUN})
    tolerancia: float = config.TOLERANCIA
    concorrencia: int = 4


def _faltando(i: Item) -> list[str]:
    return [n for n, v in (("NCM", i.ncm), ("CST do IBS/CBS", i.cst), ("cClassTrib", i.c_class_trib)) if not v]


def _operacao(nfe: Nfe, itens: list[Item], o: Opcoes) -> dict:
    if o.modo == "conferencia":
        data, com_aliq = nfe.dh_emi, nfe.dh_emi[:4] >= "2027"
    else:
        data, com_aliq = o.data_simulacao, o.data_simulacao[:4] >= "2027"
    return {
        "id": hashlib.md5((nfe.chave or str(uuid.uuid4())).encode()).hexdigest(),
        "versao": "1.0.0",
        "dhFatoGerador": data,
        "municipio": int(nfe.c_mun_fg or 0),
        "uf": nfe.uf_emit,
        "tpDoc": 55,
        "itens": [
            {"numero": i.numero, "ncm": i.ncm, "cst": i.cst, "cClassTrib": i.c_class_trib,
             "baseCalculo": float(i.base_calculo),
             **({"quantidade": float(i.quantidade)} if i.quantidade is not None else {}),
             **({"unidade": i.unidade} if i.unidade else {}),
             # Regra do motor: alíquotas nominais proibidas até 2026 (REG-036), obrigatórias desde 2027.
             **({"aliquotasNominais": o.aliquotas} if com_aliq else {})}
            for i in itens
        ],
    }


def _num(s) -> Decimal:
    try:
        return Decimal(str(s)) if s not in (None, "") else Decimal(0)
    except Exception:
        return Decimal(0)


async def diagnosticar(nfes: list[Nfe], calc: Calculadora, o: Opcoes | None = None) -> dict:
    o = o or Opcoes()
    pend: dict[tuple, dict] = {}
    diverg: list[dict] = []
    avisos: list[str] = []
    t = {"base": Decimal(0), "cbs": Decimal(0), "ibs": Decimal(0), "is": Decimal(0), "atual": Decimal(0)}
    c = {"total": 0, "calc": 0, "pend": 0, "falha": 0, "conf": 0}

    def anotar(tipo, codigo, titulo, detalhe, sugestao, item: Item):
        k = (tipo, codigo, item.c_prod, item.ncm or "")
        p = pend.get(k)
        if p:
            p["ocorrencias"] += 1
            p["valorTotal"] = r2(Decimal(str(p["valorTotal"])) + item.base_calculo)
        else:
            pend[k] = dict(tipo=tipo, codigo=codigo, titulo=titulo, detalhe=detalhe, sugestao=sugestao,
                           cProd=item.c_prod, descricao=item.descricao, ncm=item.ncm,
                           cClassTrib=item.c_class_trib, ocorrencias=1, valorTotal=r2(item.base_calculo))
        c["pend"] += 1

    sem = asyncio.Semaphore(o.concorrencia)

    async def processa(nfe: Nfe):
        por_num = {i.numero: i for i in nfe.itens}
        envia: list[Item] = []
        for i in nfe.itens:
            c["total"] += 1
            t["atual"] += i.v_icms + i.v_pis + i.v_cofins + i.v_issqn
            f = _faltando(i)
            if f:
                anotar("CADASTRO_INCOMPLETO", "CAD-001", "Cadastro fiscal incompleto", "Faltando: " + ", ".join(f),
                       "Completar a classificação tributária do produto/serviço no ERP.", i)
            else:
                envia.append(i)
        if not envia:
            return
        try:
            async with sem:
                resp = await calc.observabilidade(_operacao(nfe, envia, o))
        except CalculadoraErro as e:
            c["falha"] += 1
            avisos.append(f"NF-e {nfe.numero or nfe.chave}: {e}")
            for i in envia:
                anotar("FALHA_TECNICA", "TEC-001", "Falha ao consultar a calculadora", str(e),
                       "Repetir o diagnóstico; se persistir, verificar a calculadora.", i)
            return
        for obj in resp.get("objetos", []):
            i = por_num.get(obj.get("nObj"))
            if not i:
                continue
            est = obj.get("estadoItem")
            g = ((obj.get("tribCalc") or {}).get("IBSCBS") or {}).get("gIBSCBS") or {}
            if est in ("CALCULADO", "CALCULO_SIMULADO"):
                c["calc"] += 1
                cbs, ibs = _num((g.get("gCBS") or {}).get("vCBS")), _num(g.get("vIBS"))
                t["base"] += _num(g.get("vBC")); t["cbs"] += cbs; t["ibs"] += ibs
                t["is"] += _num(((obj.get("tribCalc") or {}).get("IS") or {}).get("vIS"))
                if o.modo == "conferencia" and (i.decl_cbs is not None or i.decl_ibs is not None):
                    c["conf"] += 1
                    d_cbs = (i.decl_cbs or Decimal(0)) - cbs
                    d_ibs = (i.decl_ibs or Decimal(0)) - ibs
                    tol = Decimal(str(o.tolerancia))
                    if abs(d_cbs) > tol or abs(d_ibs) > tol:
                        diverg.append(dict(
                            codigo="DIV-001", nota=nfe.numero or nfe.chave, item=i.numero, cProd=i.c_prod,
                            descricao=i.descricao, cbsDeclarado=r2(i.decl_cbs or 0), cbsCalculado=r2(cbs),
                            ibsDeclarado=r2(i.decl_ibs or 0), ibsCalculado=r2(ibs),
                            diferenca=r2(d_cbs + d_ibs),
                            sugestao="Comparar com o cálculo da calculadora oficial: revisar alíquota/cClassTrib "
                                     "do item e a versão da calculadora usada (arredondamentos mudam entre versões)."))
                continue
            e0 = (obj.get("erros") or [{}])[0]
            cod = e0.get("code") or est or "ERRO"
            anotar("FALHA_TECNICA" if est == "FALHA_TECNICA" else "ERRO_CALCULADORA", cod,
                   e0.get("title") or est, e0.get("detail") or "Item não calculado pela calculadora.",
                   sugestao_para(cod), i)

    await asyncio.gather(*(processa(n) for n in nfes))

    proj = t["cbs"] + t["ibs"]
    em = nfes[0] if nfes else None
    return {
        "id": str(uuid.uuid4()),
        "geradoEm": datetime.now(timezone.utc).isoformat(),
        "modo": o.modo,
        "modoCalculadora": calc.modo,
        "dataSimulacao": o.data_simulacao if o.modo == "simulacao" else None,
        "aliquotasSimulacao": o.aliquotas,
        "empresa": {"cnpj": em.emit_cnpj, "nome": em.emit_nome, "uf": em.uf_emit} if em else {},
        "notasLidas": len(nfes), "notasComFalha": c["falha"],
        "itensTotal": c["total"], "itensCalculados": c["calc"], "itensComPendencia": c["pend"],
        "itensConferidos": c["conf"],
        "totais": {
            "baseCalculo": r2(t["base"]), "cbs": r2(t["cbs"]), "ibs": r2(t["ibs"]), "is": r2(t["is"]),
            "cargaAtual": r2(t["atual"]), "cargaProjetada": r2(proj),
            "variacaoPercentual": r2((proj - t["atual"]) / t["atual"] * 100) if t["atual"] > 0 else None,
        },
        "pendencias": sorted(pend.values(), key=lambda p: -p["valorTotal"]),
        "divergencias": diverg,
        "avisos": avisos,
    }
