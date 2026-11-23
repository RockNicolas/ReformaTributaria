import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.calculadora import Calculadora, transporte_mock
from app.diagnostico import Opcoes, diagnosticar
from app.nfe import NfeInvalida, ler_nfe
from app.sugestoes import sugestao_para

XML = (Path(__file__).parent / "fixtures" / "nfe-exemplo.xml").read_bytes()


def calc():
    return Calculadora("http://mock/api", "mock", transport=transporte_mock())


def test_le_nfe():
    n = ler_nfe(XML)
    assert len(n.itens) == 4 and n.uf_emit == "SP" and n.itens[0].ncm == "25232910"
    assert n.itens[0].cst == "000" and n.itens[2].cst is None


def test_rejeita_xml_invalido_e_xxe():
    with pytest.raises(NfeInvalida):
        ler_nfe(b"nao e xml")
    with pytest.raises(NfeInvalida):
        ler_nfe(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>')


def test_simulacao():
    d = asyncio.run(diagnosticar([ler_nfe(XML)], calc()))
    assert d["itensTotal"] == 4 and d["itensCalculados"] == 2 and d["itensComPendencia"] == 2
    codigos = {p["codigo"] for p in d["pendencias"]}
    assert codigos == {"CAD-001", "REG-011"}
    assert all(p["sugestao"] for p in d["pendencias"])
    assert d["totais"]["cbs"] > 0 and d["modoCalculadora"] == "mock"


def test_conferencia_detecta_divergencia():
    n = ler_nfe(XML)
    n.itens[0].decl_cbs = n.itens[0].decl_ibs = 0  # declarou zero; calculado > 0
    n.dh_emi = "2027-03-10T10:00:00-03:00"
    d = asyncio.run(diagnosticar([n], calc(), Opcoes(modo="conferencia")))
    assert d["itensConferidos"] == 1 and d["divergencias"][0]["codigo"] == "DIV-001"


def test_conferencia_2026_omite_aliquotas():
    from app.diagnostico import _operacao
    n = ler_nfe(XML)  # emitida em 2026
    op = _operacao(n, n.itens[:1], Opcoes(modo="conferencia"))
    assert "aliquotasNominais" not in op["itens"][0]
    op2 = _operacao(n, n.itens[:1], Opcoes(modo="simulacao"))
    assert "aliquotasNominais" in op2["itens"][0]


def test_sugestao_padrao():
    assert "NCM" in sugestao_para("REG-011") and sugestao_para("XYZ")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(config, "MODO_CALCULADORA", "mock")
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_fluxo(cliente):
    r = cliente.post("/api/diagnosticos", files=[("arquivos", ("a.xml", XML))])
    assert r.status_code == 200
    d = r.json()
    h = cliente.get(f"/api/diagnosticos/{d['id']}/relatorio.html")
    assert h.status_code == 200 and "RESULTADO DE TESTE" in h.text
    assert cliente.get("/api/diagnosticos/../x").status_code in (404, 405)
    assert cliente.get("/api/diagnosticos/nao-existe").status_code == 404


def test_api_rejeita_xml_ruim(cliente):
    assert cliente.post("/api/diagnosticos", files=[("arquivos", ("a.xml", b"lixo"))]).status_code == 422


def test_validar(cliente):
    op = {"itens": [{"numero": 1, "ncm": "99999999", "cst": "000", "cClassTrib": "000001", "baseCalculo": 10}]}
    r = cliente.post("/v1/validar", json=op).json()
    assert r["valido"] is False and r["itens"][0]["erros"][0]["sugestao"]
    assert cliente.post("/v1/validar", json={"itens": []}).status_code == 422


def test_auth_e_limite(cliente, monkeypatch):
    monkeypatch.setattr(config, "API_KEYS", {"segredo"})
    assert cliente.post("/v1/validar", json={"itens": [{}]}).status_code == 401
    ok = {"X-API-Key": "segredo"}
    op = {"itens": [{"numero": 1, "ncm": "25232910", "cst": "000", "cClassTrib": "000001", "baseCalculo": 10}]}
    assert cliente.post("/v1/validar", json=op, headers=ok).status_code == 200
    monkeypatch.setattr(config, "LIMITE_POR_MINUTO", 1)
    assert cliente.post("/v1/validar", json=op, headers=ok).status_code == 429


def test_variacao_compara_so_itens_calculados():
    d = asyncio.run(diagnosticar([ler_nfe(XML)], calc()))
    assert d["amostraParcial"] is True
    # itens calculados: 1 e 2 -> ICMS+PIS+COFINS = 180+16.5+76 + 360+33+152
    assert d["totais"]["cargaAtual"] == 817.5 and d["totais"]["cargaAtualTodosItens"] == 817.5


def test_sugestao_e_csv():
    from app.sugestao import para_csv, sugerir
    r = asyncio.run(sugerir(calc(), [{"ncm": "10061010", "produto": "Arroz"}, {"ncm": "25232910", "produto": "x"}], "2027-03-10"))
    st = {x["ncm"]: x["status"] for x in r}
    assert st == {"10061010": "REVISAR", "25232910": "PADRAO_PROVAVEL"}
    assert "ncm;produto_exemplo" in para_csv(r)


def test_endpoints_novos(cliente):
    d = cliente.post("/api/diagnosticos", files=[("arquivos", ("a.xml", XML))]).json()
    r = cliente.get(f"/api/diagnosticos/{d['id']}/sugestoes.csv")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    s = cliente.post("/v1/sugerir-classificacao", json={"ncms": ["10061010"]}).json()
    assert s["sugestoes"][0]["status"] == "REVISAR"
    assert cliente.post("/v1/sugerir-classificacao", json={"ncms": []}).status_code == 422
    v = cliente.post("/v1/validar-nfe", files={"arquivo": ("a.xml", XML)}).json()
    assert v["valida"] is False and v["pendencias"]


def test_monitor_processa_uma_vez(tmp_path):
    import shutil
    from app.monitor import ciclo
    ent, sai = tmp_path / "e", tmp_path / "s"
    ent.mkdir()
    shutil.copy(Path(__file__).parent / "fixtures" / "nfe-exemplo.xml", ent / "n1.xml")
    (ent / "ruim.xml").write_text("lixo")
    r1 = asyncio.run(ciclo(calc(), ent, sai, None, "simulacao"))
    assert r1["pendencias"] == 2 and any(p.suffix == ".html" for p in sai.iterdir())
    assert asyncio.run(ciclo(calc(), ent, sai, None, "simulacao")) is None  # nada novo


def test_planilha_de_produtos(cliente):
    csv_ = (Path(__file__).parent / "fixtures" / "produtos-exemplo.csv").read_bytes()
    r = cliente.post("/api/planilha", files={"arquivo": ("p.csv", csv_)}, data={"uf": "SP"})
    assert r.status_code == 200
    import json
    res = json.loads(r.headers["x-resumo"])
    assert res == {"total": 4, "prontos": 1, "revisar": 1, "com_erro": 1, "sem_ncm": 1}
    assert "cst;cclasstrib" in r.text
    assert cliente.post("/api/planilha", files={"arquivo": ("p.csv", b"a;b\n1;2")}).status_code == 422


def test_sienge_extrai_e_gera_cadastro(cliente):
    import httpx, json
    from app.conectores.sienge import ConectorErro, extrair_produtos
    itens = [{"fiscalProductCode": "P1", "fiscalProductDescription": "Arroz", "ncmCode": "1006.10.10", "cfop": "5102"},
             {"fiscalProductCode": "P1", "fiscalProductDescription": "Arroz", "ncmCode": "10061010"},
             {"fiscalProductCode": "P2", "fiscalProductDescription": "Cimento", "ncmCode": "25232910"}]
    assert [p["ncm"] for p in extrair_produtos(itens)] == ["10061010", "25232910"]
    with pytest.raises(ConectorErro):
        extrair_produtos([{"foo": 1}])

    def h(req):
        assert req.url.path.endswith("/bulk-data/v1/invoice-itens") and req.url.params["startDate"] == "2026-10-01"
        return httpx.Response(200, json={"data": itens})
    cliente.app.state.sienge_transport = httpx.MockTransport(h)
    r = cliente.post("/api/sienge/cadastro-fiscal", data={"subdominio": "x", "usuario": "u", "senha": "s",
                                                         "inicio": "2026-10-01", "fim": "2026-10-31"})
    assert r.status_code == 200 and json.loads(r.headers["x-resumo"])["total"] == 2
    cliente.app.state.sienge_transport = httpx.MockTransport(lambda q: httpx.Response(401))
    assert cliente.post("/api/sienge/cadastro-fiscal", data={"subdominio": "x", "usuario": "u", "senha": "s",
                                                            "inicio": "a", "fim": "b"}).status_code == 502


SPED = ("|0000|017|0|01102026|31102026|EMPRESA|12345678000195||SP|||A|1|\n"
        "|0200|PA-001|Arroz 5kg|7894494081163||UN|04|10061010||||18|1902100|\n"
        "|0200|PA-002|Cimento|||UN|00|2523.29.10||||18|\n"
        "|0200|SV-001|Frete|||UN|09||||||\n|9999|5|\n").encode("latin-1")


def test_sped_extrai_0200():
    from app.conectores.sped import SpedInvalido, extrair_produtos
    p = extrair_produtos(SPED)
    assert [(x["codigo"], x["ncm"]) for x in p] == [("PA-001", "10061010"), ("PA-002", "25232910")]
    with pytest.raises(SpedInvalido):
        extrair_produtos(b"nao e sped")


def test_endpoint_sped_e_zip_e_omie(cliente):
    import httpx, io, json, zipfile
    r = cliente.post("/api/sped/cadastro-fiscal", files={"arquivo": ("efd.txt", SPED)})
    assert r.status_code == 200 and json.loads(r.headers["x-resumo"])["total"] == 2
    assert cliente.post("/api/sped/cadastro-fiscal", files={"arquivo": ("x.txt", b"lixo")}).status_code == 422

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.xml", XML)
        z.writestr("b.xml", "lixo")
    d = cliente.post("/api/diagnosticos", files=[("arquivos", ("lote.zip", buf.getvalue()))]).json()
    assert d["notasLidas"] == 1 and any("b.xml" in a for a in d["avisos"])

    def h(req):
        corpo = json.loads(req.content)
        assert corpo["call"] == "ListarProdutos"
        return httpx.Response(200, json={"pagina": 1, "total_de_paginas": 1, "produto_servico_cadastro": [
            {"codigo": "A1", "descricao": "Arroz", "ncm": "1006.10.10"}]})
    cliente.app.state.omie_transport = httpx.MockTransport(h)
    r = cliente.post("/api/omie/cadastro-fiscal", data={"app_key": "k", "app_secret": "s"})
    assert r.status_code == 200 and json.loads(r.headers["x-resumo"])["total"] == 1
