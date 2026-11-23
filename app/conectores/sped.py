"""Conector universal: SPED Fiscal (EFD ICMS/IPI) ou EFD Contribuições.

Todo contador e todo ERP geram esse arquivo. O Registro 0200 (tabela de itens) traz código, descrição e NCM:
|0200|COD_ITEM|DESCR_ITEM|COD_BARRA|COD_ANT_ITEM|UNID_INV|TIPO_ITEM|COD_NCM|EXT_IPI|COD_GEN|COD_LST|ALIQ_ICMS|CEST|
Funciona com qualquer sistema (Sienge, Totvs RM, Senior, Domínio, Mega, UAU...) sem integração específica.
"""
import re

TIPO_SERVICO = "09"  # TIPO_ITEM 09 = serviço (não tem NCM; fica de fora desta classificação)


class SpedInvalido(ValueError):
    pass


def extrair_produtos(conteudo: bytes) -> list[dict]:
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")  # padrão do arquivo SPED
    if "|0000|" not in texto[:5000]:
        raise SpedInvalido("O arquivo não parece um SPED (registro 0000 não encontrado no início).")
    vistos: dict[str, dict] = {}
    for linha in texto.splitlines():
        if not linha.startswith("|0200|"):
            continue
        c = linha.split("|")  # ['', '0200', COD_ITEM, DESCR_ITEM, COD_BARRA, COD_ANT, UNID, TIPO, COD_NCM, ...]
        if len(c) < 9:
            continue
        tipo = c[7].strip()
        if tipo == TIPO_SERVICO:
            continue
        cod = c[2].strip()
        vistos.setdefault(cod, {"codigo": cod, "descricao": c[3].strip(), "ncm": re.sub(r"\D", "", c[8])})
    if not vistos:
        raise SpedInvalido("Nenhum item (registro 0200) encontrado no arquivo.")
    return list(vistos.values())
