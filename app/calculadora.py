"""Cliente assíncrono da calculadora oficial (Java) e simulador de teste (mock)."""
import asyncio

import httpx


class CalculadoraErro(RuntimeError):
    pass


class Calculadora:
    def __init__(self, base_url: str, modo: str = "oficial", timeout: float = 30, transport=None):
        self.base_url = base_url.rstrip("/")
        self.modo = modo
        self._c = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def observabilidade(self, operacao: dict, tentativas: int = 3) -> dict:
        url = f"{self.base_url}/calculadora/observabilidade/regime-geral"
        ultimo: Exception | None = None
        for t in range(tentativas):
            try:
                r = await self._c.post(url, json=operacao)
                if r.status_code >= 500:
                    raise CalculadoraErro(f"HTTP {r.status_code}: {r.text[:300]}")
                if r.status_code >= 400:
                    # erro de contrato (4xx): repetir não adianta
                    raise CalculadoraErro(f"HTTP {r.status_code}: {r.text[:300]}")
                return r.json()
            except httpx.HTTPError as e:
                ultimo = CalculadoraErro(f"Sem resposta da calculadora em {self.base_url}: {e}")
            except CalculadoraErro as e:
                if "HTTP 4" in str(e):
                    raise
                ultimo = e
            await asyncio.sleep(0.3 * (t + 1))
        raise ultimo or CalculadoraErro("falha desconhecida")

    async def versao(self) -> dict:
        r = await self._c.get(f"{self.base_url}/calculadora/dados-abertos/versao")
        r.raise_for_status()
        return r.json()

    async def dados_abertos(self, caminho: str, **params):
        """GET em /calculadora/dados-abertos/<caminho>; devolve JSON ou levanta CalculadoraErro."""
        url = f"{self.base_url}/calculadora/dados-abertos/{caminho.lstrip('/')}"
        try:
            r = await self._c.get(url, params=params)
        except httpx.HTTPError as e:
            raise CalculadoraErro(f"Sem resposta da calculadora: {e}") from e
        if r.status_code >= 400:
            raise CalculadoraErro(f"HTTP {r.status_code} em {caminho}: {r.text[:200]}")
        return r.json()

    async def fechar(self):
        await self._c.aclose()


# ---- Simulador de TESTE: NÃO usa regras reais. Resultado sai marcado como "mock". ----
REDUCAO = {"200003": 100, "200028": 60}


def _item_mock(i: dict) -> dict:
    n = i["numero"]
    if not i.get("ncm") and not i.get("nbs"):
        return {"nObj": n, "estadoItem": "INCONSISTENCIA_ENTRADA",
                "erros": [{"code": "REG-033", "title": "Nomenclatura obrigatória não informada", "detail": "Informe NCM ou NBS."}]}
    if (i.get("ncm") or "").startswith("99"):
        return {"nObj": n, "estadoItem": "INCONSISTENCIA_ENTRADA",
                "erros": [{"code": "REG-011", "title": "NCM não vinculada",
                           "detail": f"NCM {i['ncm']} não vinculada à classificação {i['cClassTrib']}"}]}
    f = 1 - REDUCAO.get(i["cClassTrib"], 0) / 100
    a = i.get("aliquotasNominais") or {"cbs": 0, "ibsEstadual": 0, "ibsMunicipal": 0}
    b = float(i["baseCalculo"])
    return {"nObj": n, "estadoItem": "CALCULO_SIMULADO", "tribCalc": {"IBSCBS": {"gIBSCBS": {
        "vBC": f"{b:.2f}", "vIBS": f"{b * f * (a['ibsEstadual'] + a['ibsMunicipal']) / 100:.2f}",
        "gCBS": {"vCBS": f"{b * f * a['cbs'] / 100:.2f}"}}}}}


def transporte_mock() -> httpx.MockTransport:
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/versao"):
            return httpx.Response(200, json={"aplicacao": "mock"})
        p = req.url.path
        if p.endswith("/situacoes-tributarias/cbs-ibs"):
            return httpx.Response(200, json=[
                {"codigo": "000", "descricao": "Tributação integral", "classificacoesTributarias": [
                    {"codigo": "000001", "descricao": "Situações tributadas integralmente"}]},
                {"codigo": "200", "descricao": "Alíquota reduzida", "classificacoesTributarias": [
                    {"codigo": "200003", "descricao": "Cesta básica (mock)"}]}])
        if "/nomenclatura/" in p:
            return httpx.Response(200, json={"nomenclatura": "NCM" if p.endswith("200003") else "SEM"})
        if p.endswith("/classificacoes-tributarias/ncm-aplicavel"):
            q = req.url.params
            return httpx.Response(200, json={"valido": q["ncm"].startswith("1006") and q["cClassTrib"] == "200003"})
        if req.url.path.endswith("/observabilidade/regime-geral"):
            import json
            op = json.loads(req.content)
            return httpx.Response(200, json={"objetos": [_item_mock(i) for i in op["itens"]]})
        return httpx.Response(404, json={"erro": "rota não existe no mock"})
    return httpx.MockTransport(h)
