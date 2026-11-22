"""Leitura de XML de NF-e (55) / NFC-e (65). Usa defusedxml (bloqueia XXE) e Decimal."""
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from .modelos import Item, Nfe


class NfeInvalida(ValueError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _filho(el: Element | None, nome: str) -> Element | None:
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == nome:
            return c
    return None


def _caminho(el: Element | None, *nomes: str) -> Element | None:
    for n in nomes:
        el = _filho(el, n)
    return el


def _achar(el: Element | None, nome: str) -> Element | None:
    """Primeiro descendente com a tag (ex.: vICMS dentro de ICMS00/ICMS20...)."""
    if el is None:
        return None
    for e in el.iter():
        if _local(e.tag) == nome:
            return e
    return None


def _txt(el: Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _dec(el: Element | None) -> Decimal:
    t = _txt(el)
    if t is None:
        return Decimal(0)
    try:
        return Decimal(t)
    except InvalidOperation:
        return Decimal(0)


def _dec_opt(el: Element | None) -> Decimal | None:
    t = _txt(el)
    if t is None:
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def ler_nfe(xml: bytes | str) -> Nfe:
    try:
        raiz = ET.fromstring(xml)
    except (ET.ParseError, DefusedXmlException) as e:
        raise NfeInvalida("Arquivo não é um XML válido (ou contém construções não permitidas).") from e

    inf = _achar(raiz, "infNFe")
    if inf is None:
        raise NfeInvalida("XML não contém uma NF-e/NFC-e (infNFe não encontrado).")

    ide, emit = _filho(inf, "ide"), _filho(inf, "emit")
    itens: list[Item] = []
    for pos, det in enumerate((c for c in inf if _local(c.tag) == "det"), start=1):
        prod, imp = _filho(det, "prod"), _filho(det, "imposto")
        v_prod = _dec(_filho(prod, "vProd"))
        base = (
            v_prod + _dec(_filho(prod, "vFrete")) + _dec(_filho(prod, "vSeg"))
            + _dec(_filho(prod, "vOutro")) - _dec(_filho(prod, "vDesc"))
        )
        ibscbs = _filho(imp, "IBSCBS")
        g = _filho(ibscbs, "gIBSCBS")
        try:
            numero = int(det.get("nItem", pos))
        except ValueError:
            numero = pos
        itens.append(
            Item(
                numero=numero,
                c_prod=_txt(_filho(prod, "cProd")) or f"item-{pos}",
                descricao=_txt(_filho(prod, "xProd")) or "",
                base_calculo=max(Decimal(0), base).quantize(Decimal("0.01")),
                ncm=_txt(_filho(prod, "NCM")),
                unidade=_txt(_filho(prod, "uCom")),
                quantidade=_dec_opt(_filho(prod, "qCom")),
                cst=_txt(_filho(ibscbs, "CST")),
                c_class_trib=_txt(_filho(ibscbs, "cClassTrib")),
                v_icms=_dec(_achar(_filho(imp, "ICMS"), "vICMS")),
                v_pis=_dec(_achar(_filho(imp, "PIS"), "vPIS")),
                v_cofins=_dec(_achar(_filho(imp, "COFINS"), "vCOFINS")),
                v_issqn=_dec(_achar(_filho(imp, "ISSQN"), "vISSQN")),
                decl_cbs=_dec_opt(_caminho(g, "gCBS", "vCBS")),
                decl_ibs=_dec_opt(_filho(g, "vIBS")),
            )
        )
    if not itens:
        raise NfeInvalida("NF-e sem itens (det).")

    return Nfe(
        chave=(inf.get("Id") or "").removeprefix("NFe"),
        numero=_txt(_filho(ide, "nNF")),
        dh_emi=_txt(_filho(ide, "dhEmi")) or _txt(_filho(ide, "dEmi")) or "",
        c_mun_fg=_txt(_filho(ide, "cMunFG")) or "",
        uf_emit=_txt(_caminho(emit, "enderEmit", "UF")) or "",
        emit_cnpj=_txt(_filho(emit, "CNPJ")) or _txt(_filho(emit, "CPF")) or "",
        emit_nome=_txt(_filho(emit, "xNome")) or "",
        itens=itens,
    )
