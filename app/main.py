"""API FastAPI: diagnóstico em lote, conferência e validação de operação."""
import io
import json
import logging
import zipfile
import re
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import config
from .calculadora import Calculadora, CalculadoraErro, transporte_mock
from .diagnostico import Opcoes, diagnosticar
from . import planilha as pl
from .conectores import omie as omie_con
from .conectores import sped as sped_con
from .conectores.sienge import ConectorErro, Sienge, extrair_produtos
from .nfe import NfeInvalida, ler_nfe
from .relatorio import renderizar
from .seguranca import exigir_acesso
from .sugestao import para_csv, sugerir
from .sugestoes import sugestao_para

log = logging.getLogger("reforma")
WEB = Path(__file__).resolve().parent.parent / "web"
_UUID = re.compile(r"^[0-9a-f-]{36}$")
_guardados: "OrderedDict[str, dict]" = OrderedDict()  # em memória; troque por banco em produção


def _xmls_do_zip(corpo: bytes, max_arquivos: int = 2000, max_total: int = 200 * 1024 * 1024):
    """Lê os .xml de um ZIP com proteção contra zip bomb (limite de quantidade e de tamanho descompactado)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(corpo))
    except zipfile.BadZipFile as e:
        raise ValueError("ZIP inválido.") from e
    infos = [i for i in z.infolist() if i.filename.lower().endswith(".xml") and not i.is_dir()]
    if len(infos) > max_arquivos or sum(i.file_size for i in infos) > max_total:
        raise ValueError("ZIP grande demais (máx. 2000 XMLs / 200 MB descompactado).")
    return [(i.filename, z.read(i)) for i in infos]


@asynccontextmanager
async def ciclo(app: FastAPI):
    mock = config.MODO_CALCULADORA == "mock"
    app.state.calc = Calculadora(config.CALCULADORA_URL, config.MODO_CALCULADORA, config.TIMEOUT_S,
                                 transport=transporte_mock() if mock else None)
    yield
    await app.state.calc.fechar()


app = FastAPI(title="Reforma Tributária — Diagnóstico e Validação", version="0.2.0", lifespan=ciclo)


@app.get("/saude")
async def saude():
    try:
        v = await app.state.calc.versao()
        return {"api": "ok", "calculadora": "ok", "versao": v, "modo": app.state.calc.modo}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Calculadora indisponível: {e}")


@app.get("/", include_in_schema=False)
async def inicio():
    return FileResponse(WEB / "index.html")


@app.post("/api/diagnosticos", dependencies=[Depends(exigir_acesso)])
async def criar_diagnostico(
    arquivos: list[UploadFile] = File(...),
    modo: str = Form("simulacao"),
    data_simulacao: str | None = Form(None),
):
    if modo not in ("simulacao", "conferencia"):
        raise HTTPException(400, "modo deve ser 'simulacao' ou 'conferencia'.")
    if len(arquivos) > 2000:
        raise HTTPException(413, "Máximo de 2000 XMLs por diagnóstico.")
    nfes, erros = [], []
    for f in arquivos:
        corpo = await f.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(corpo) > config.MAX_UPLOAD_MB * 1024 * 1024:
            erros.append(f"{f.filename}: maior que {config.MAX_UPLOAD_MB} MB")
            continue
        if (f.filename or "").lower().endswith(".zip"):
            try:
                for nome, xml in _xmls_do_zip(corpo):
                    try:
                        nfes.append(ler_nfe(xml))
                    except NfeInvalida as e:
                        erros.append(f"{nome}: {e}")
            except ValueError as e:
                erros.append(f"{f.filename}: {e}")
            continue
        try:
            nfes.append(ler_nfe(corpo))
        except NfeInvalida as e:
            erros.append(f"{f.filename}: {e}")
    if not nfes:
        raise HTTPException(422, {"mensagem": "Nenhuma NF-e válida.", "erros": erros})
    o = Opcoes(modo=modo, **({"data_simulacao": data_simulacao} if data_simulacao else {}))
    d = await diagnosticar(nfes, app.state.calc, o)
    d["avisos"] = erros + d["avisos"]
    _guardados[d["id"]] = d
    while len(_guardados) > 200:
        _guardados.popitem(last=False)
    return d


def _obter(id_: str) -> dict:
    if not _UUID.match(id_) or id_ not in _guardados:
        raise HTTPException(404, "Diagnóstico não encontrado.")
    return _guardados[id_]


@app.get("/api/diagnosticos/{id_}", dependencies=[Depends(exigir_acesso)])
async def obter(id_: str):
    return _obter(id_)


@app.get("/api/diagnosticos/{id_}/relatorio.html", response_class=HTMLResponse,
         dependencies=[Depends(exigir_acesso)])
async def relatorio(id_: str, marca: str = ""):
    return renderizar(_obter(id_), marca[:80])


@app.post("/v1/validar", dependencies=[Depends(exigir_acesso)])
async def validar(operacao: dict):
    """Valida uma operação (mesmo corpo da calculadora) e devolve erros com ação sugerida."""
    if not operacao.get("itens"):
        raise HTTPException(422, "A operação precisa ter ao menos um item em 'itens'.")
    try:
        resp = await app.state.calc.observabilidade(operacao)
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível ou rejeitou a requisição: {e}")
    itens, ok = [], True
    for obj in resp.get("objetos", []):
        bons = obj.get("estadoItem") in ("CALCULADO", "CALCULO_SIMULADO")
        ok &= bons
        itens.append({
            "numero": obj.get("nObj"), "estado": obj.get("estadoItem"), "valido": bons,
            "erros": [{"codigo": x.get("code"), "titulo": x.get("title"), "detalhe": x.get("detail"),
                       "campo": x.get("pointer"), "sugestao": sugestao_para(x.get("code", ""))}
                      for x in obj.get("erros") or []],
        })
    return {"valido": ok, "itens": itens, "modoCalculadora": app.state.calc.modo}


CODIGOS_CADASTRO = {"CAD-001", "REG-002", "REG-004", "REG-005", "REG-006", "REG-011", "REG-029", "REG-030", "REG-033"}


@app.get("/api/diagnosticos/{id_}/sugestoes.csv", dependencies=[Depends(exigir_acesso)])
async def sugestoes_csv(id_: str):
    """Planilha de cadastro sugerido (NCM -> CST + cClassTrib) para os itens com pendência."""
    d = _obter(id_)
    itens = [{"ncm": p["ncm"], "produto": p["descricao"]} for p in d["pendencias"]
             if p.get("ncm") and p["codigo"] in CODIGOS_CADASTRO]
    try:
        linhas = await sugerir(app.state.calc, itens, (d.get("dataSimulacao") or "")[:10] or None)
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível: {e}")
    return Response(para_csv(linhas), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cadastro-sugerido-{id_[:8]}.csv"'})


@app.post("/v1/sugerir-classificacao", dependencies=[Depends(exigir_acesso)])
async def sugerir_classificacao(corpo: dict):
    """{"ncms": ["10061010", ...], "data": "2027-03-10"} -> candidatas por NCM."""
    ncms = corpo.get("ncms") or []
    if not isinstance(ncms, list) or not ncms or len(ncms) > 500:
        raise HTTPException(422, "Envie 'ncms' como lista de 1 a 500 NCMs.")
    try:
        linhas = await sugerir(app.state.calc, [{"ncm": str(n), "produto": ""} for n in ncms], corpo.get("data"))
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível: {e}")
    return {"sugestoes": linhas}


@app.post("/v1/validar-nfe", dependencies=[Depends(exigir_acesso)])
async def validar_nfe(arquivo: UploadFile = File(...)):
    """Validação ANTES de emitir/escriturar: confere a NF-e (XML) item a item na data da própria nota."""
    corpo = await arquivo.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        nfe = ler_nfe(corpo)
    except NfeInvalida as e:
        raise HTTPException(422, str(e))
    d = await diagnosticar([nfe], app.state.calc, Opcoes(modo="conferencia"))
    return {
        "valida": not d["pendencias"] and not d["divergencias"] and not d["avisos"],
        "itens": d["itensTotal"], "pendencias": d["pendencias"], "divergencias": d["divergencias"],
        "avisos": d["avisos"], "modoCalculadora": d["modoCalculadora"],
    }


@app.post("/api/planilha", dependencies=[Depends(exigir_acesso)])
async def planilha_produtos(arquivo: UploadFile = File(...), uf: str = Form("SP"),
                            municipio: int = Form(3550308), data: str = Form("2027-03-10")):
    """Planilha de produtos (CSV com NCM) -> CSV de cadastro fiscal sugerido e conferido pelo motor."""
    corpo = await arquivo.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        produtos = pl.ler_csv(corpo)
        linhas = await pl.processar(app.state.calc, produtos, uf.upper()[:2], municipio, data)
    except pl.PlanilhaInvalida as e:
        raise HTTPException(422, str(e))
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível: {e}")
    r = pl.resumo(linhas)
    return Response(pl.para_csv(linhas), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="cadastro-fiscal-pronto.csv"',
        "X-Resumo": json.dumps(r),
        "Access-Control-Expose-Headers": "X-Resumo"})


@app.post("/api/sienge/cadastro-fiscal", dependencies=[Depends(exigir_acesso)])
async def sienge_cadastro_fiscal(subdominio: str = Form(...), usuario: str = Form(...), senha: str = Form(...),
                                 inicio: str = Form(...), fim: str = Form(...), uf: str = Form("SP"),
                                 municipio: int = Form(3550308), data: str = Form("2027-03-10")):
    """Puxa os itens de nota do Sienge no período, extrai os produtos (NCM) e devolve o cadastro fiscal conferido.
    As credenciais do Sienge são usadas só nesta chamada (não são gravadas nem registradas em log)."""
    sg = Sienge(subdominio, usuario, senha, transport=getattr(app.state, "sienge_transport", None))
    try:
        produtos = extrair_produtos(await sg.itens_notas(inicio, fim))
        if not produtos:
            raise HTTPException(404, "O Sienge não devolveu itens de nota nesse período.")
        linhas = await pl.processar(app.state.calc, produtos, uf.upper()[:2], municipio, data)
    except ConectorErro as e:
        raise HTTPException(502, str(e))
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível: {e}")
    finally:
        await sg.fechar()
    return Response(pl.para_csv(linhas), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="sienge-cadastro-fiscal.csv"',
        "X-Resumo": json.dumps(pl.resumo(linhas)), "Access-Control-Expose-Headers": "X-Resumo"})


async def _entregar(produtos: list[dict], nome: str, uf: str, municipio: int, data: str) -> Response:
    if not produtos:
        raise HTTPException(404, "Nenhum produto encontrado na origem informada.")
    try:
        linhas = await pl.processar(app.state.calc, produtos, uf.upper()[:2], municipio, data)
    except CalculadoraErro as e:
        raise HTTPException(502, f"Calculadora indisponível: {e}")
    return Response(pl.para_csv(linhas), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{nome}-cadastro-fiscal.csv"',
        "X-Resumo": json.dumps(pl.resumo(linhas)), "Access-Control-Expose-Headers": "X-Resumo"})


@app.post("/api/sped/cadastro-fiscal", dependencies=[Depends(exigir_acesso)])
async def sped_cadastro_fiscal(arquivo: UploadFile = File(...), uf: str = Form("SP"),
                               municipio: int = Form(3550308), data: str = Form("2027-03-10")):
    """Universal: o contador envia o SPED (EFD ICMS/IPI ou Contribuições); lemos o Registro 0200 (itens + NCM)."""
    corpo = await arquivo.read(config.MAX_UPLOAD_MB * 5 * 1024 * 1024 + 1)  # SPED costuma ser grande
    try:
        produtos = sped_con.extrair_produtos(corpo)
    except sped_con.SpedInvalido as e:
        raise HTTPException(422, str(e))
    return await _entregar(produtos, "sped", uf, municipio, data)


@app.post("/api/omie/cadastro-fiscal", dependencies=[Depends(exigir_acesso)])
async def omie_cadastro_fiscal(app_key: str = Form(...), app_secret: str = Form(...), uf: str = Form("SP"),
                               municipio: int = Form(3550308), data: str = Form("2027-03-10")):
    """Lê os produtos do Omie (credenciais usadas só nesta chamada) e devolve o cadastro fiscal conferido."""
    try:
        produtos = await omie_con.listar_produtos(app_key, app_secret,
                                                  transport=getattr(app.state, "omie_transport", None))
    except ConectorErro as e:
        raise HTTPException(502, str(e))
    return await _entregar(produtos, "omie", uf, municipio, data)
