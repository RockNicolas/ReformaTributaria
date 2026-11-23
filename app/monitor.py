"""Monitor de pasta: processa XMLs novos, gera relatório + CSV e avisa por webhook se houver problema.

Uso:  python -m app.monitor --entrada ./entrada --saida ./saida [--webhook URL] [--intervalo 300] [--uma-vez]
Cada XML é processado uma vez (controle por hash em saida/.processados.json).
"""
import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from . import config
from .calculadora import Calculadora, transporte_mock
from .diagnostico import Opcoes, diagnosticar
from .nfe import NfeInvalida, ler_nfe
from .relatorio import renderizar
from .sugestao import para_csv, sugerir

log = logging.getLogger("monitor")
CODIGOS_CADASTRO = {"CAD-001", "REG-002", "REG-004", "REG-005", "REG-006", "REG-011", "REG-029", "REG-030", "REG-033"}


async def ciclo(calc: Calculadora, entrada: Path, saida: Path, webhook: str | None, modo: str) -> dict | None:
    saida.mkdir(parents=True, exist_ok=True)
    estado_arq = saida / ".processados.json"
    vistos: set[str] = set(json.loads(estado_arq.read_text())) if estado_arq.exists() else set()
    novos, nfes, erros = [], [], []
    for f in sorted(entrada.glob("*.xml")):
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        if h in vistos:
            continue
        try:
            nfes.append(ler_nfe(f.read_bytes()))
            novos.append(h)
        except NfeInvalida as e:
            erros.append(f"{f.name}: {e}")
            novos.append(h)  # não reprocessar arquivo inválido a cada ciclo
    if not nfes and not erros:
        return None
    resumo = None
    if nfes:
        d = await diagnosticar(nfes, calc, Opcoes(modo=modo))
        d["avisos"] = erros + d["avisos"]
        base = saida / datetime.now().strftime("%Y%m%d-%H%M%S")
        base.with_suffix(".html").write_text(renderizar(d), encoding="utf-8")
        itens = [{"ncm": p["ncm"], "produto": p["descricao"]} for p in d["pendencias"]
                 if p.get("ncm") and p["codigo"] in CODIGOS_CADASTRO]
        if itens:
            try:
                base.with_suffix(".csv").write_text(para_csv(await sugerir(calc, itens)), encoding="utf-8")
            except Exception as e:  # noqa: BLE001 - sugestão é complemento; não derruba o ciclo
                log.warning("Sugestões não geradas: %s", e)
        resumo = {"processadoEm": datetime.now().isoformat(), "notas": d["notasLidas"],
                  "itens": d["itensTotal"], "pendencias": len(d["pendencias"]),
                  "divergencias": len(d["divergencias"]), "avisos": d["avisos"][:5],
                  "relatorio": base.with_suffix(".html").name}
        base.with_suffix(".json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        if webhook and (resumo["pendencias"] or resumo["divergencias"] or resumo["avisos"]):
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    await c.post(webhook, json=resumo)
            except httpx.HTTPError as e:
                log.warning("Webhook falhou: %s", e)
    elif erros:
        resumo = {"avisos": erros}
    estado_arq.write_text(json.dumps(sorted(vistos | set(novos))))
    return resumo


async def principal():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entrada", default="./entrada")
    ap.add_argument("--saida", default="./saida")
    ap.add_argument("--webhook", default=None)
    ap.add_argument("--intervalo", type=int, default=300)
    ap.add_argument("--modo", choices=["simulacao", "conferencia"], default="conferencia")
    ap.add_argument("--uma-vez", action="store_true")
    a = ap.parse_args()
    mock = config.MODO_CALCULADORA == "mock"
    calc = Calculadora(config.CALCULADORA_URL, config.MODO_CALCULADORA, config.TIMEOUT_S,
                       transport=transporte_mock() if mock else None)
    Path(a.entrada).mkdir(parents=True, exist_ok=True)
    try:
        while True:
            try:
                r = await ciclo(calc, Path(a.entrada), Path(a.saida), a.webhook, a.modo)
                if r:
                    log.info("Ciclo: %s", r)
            except Exception as e:  # noqa: BLE001 - monitor não pode morrer por um ciclo ruim
                log.error("Ciclo falhou: %s", e)
            if a.uma_vez:
                break
            await asyncio.sleep(a.intervalo)
    finally:
        await calc.fechar()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(principal())
