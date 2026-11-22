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
