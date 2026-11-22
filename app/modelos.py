"""Modelos de dados internos."""
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Item:
    numero: int
    c_prod: str
    descricao: str
    base_calculo: Decimal
    ncm: str | None = None
    cst: str | None = None
    c_class_trib: str | None = None
    unidade: str | None = None
    quantidade: Decimal | None = None
    v_icms: Decimal = Decimal(0)
    v_pis: Decimal = Decimal(0)
    v_cofins: Decimal = Decimal(0)
    v_issqn: Decimal = Decimal(0)
    # Valores de IBS/CBS declarados na nota (quando já vierem no XML)
    decl_cbs: Decimal | None = None
    decl_ibs: Decimal | None = None


@dataclass
class Nfe:
    chave: str
    dh_emi: str
    c_mun_fg: str
    uf_emit: str
    emit_cnpj: str
    emit_nome: str
    itens: list[Item] = field(default_factory=list)
    numero: str | None = None
