"""Relatório HTML do diagnóstico (imprimível; use Imprimir > Salvar como PDF)."""
from datetime import datetime
from html import escape as e


def brl(n: float) -> str:
    return "R$ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(n: float) -> str:
    return f"{n:g}".replace(".", ",")


def renderizar(d: dict, marca: str = "") -> str:
    t, a = d["totais"], d["aliquotasSimulacao"]
    conf = d["modo"] == "conferencia"
    var = "—" if (t["variacaoPercentual"] is None or conf) else f"{t['variacaoPercentual']:+g}%".replace(".", ",")
    mock = ('<div class="aviso teste"><strong>RESULTADO DE TESTE.</strong> Gerado por simulador, não pela '
            'calculadora da Receita Federal. Não use com clientes.</div>') if d["modoCalculadora"] == "mock" else ""
    linhas = "".join(
        f'<tr><td><strong>{e(p["descricao"] or p["cProd"])}</strong><br><span class="mut">cód. {e(p["cProd"])}'
        f'{" · NCM " + e(p["ncm"]) if p["ncm"] else ""}</span></td>'
        f'<td>{e(p["codigo"])} — {e(p["titulo"])}<br><span class="mut">{e(p["detalhe"])}</span></td>'
        f'<td>{e(p["sugestao"])}</td><td class="num">{p["ocorrencias"]}</td><td class="num">{brl(p["valorTotal"])}</td></tr>'
        for p in d["pendencias"][:60])
    div = ""
    if conf:
        rows = "".join(
            f'<tr><td>NF {e(str(x["nota"]))} · item {x["item"]}<br><span class="mut">{e(x["descricao"])}</span></td>'
            f'<td class="num">{brl(x["cbsDeclarado"] + x["ibsDeclarado"])}</td>'
            f'<td class="num">{brl(x["cbsCalculado"] + x["ibsCalculado"])}</td>'
            f'<td class="num">{brl(x["diferenca"])}</td></tr>' for x in d["divergencias"][:100])
        div = (f'<h2>Divergências: declarado × calculado ({d["itensConferidos"]} itens conferidos)</h2>'
               + (f'<table><thead><tr><th>Item</th><th class="num">Declarado</th><th class="num">Calculado</th>'
                  f'<th class="num">Diferença</th></tr></thead><tbody>{rows}</tbody></table>'
                  if rows else "<p>Nenhuma divergência acima da tolerância.</p>"))
    parcial = (f'<div class="aviso"><strong>Comparação parcial.</strong> Carga atual e projetada consideram apenas os '
               f'{d["itensCalculados"]} de {d["itensTotal"]} itens calculados; os demais têm pendência. '
               f'Carga atual de todos os itens: {brl(t["cargaAtualTodosItens"])}.</div>') if d.get("amostraParcial") else ""
    sim = ("" if conf else
           f'<div class="aviso"><strong>Estimativa.</strong> Simulação para fato gerador em {e(d["dataSimulacao"][:10])}, '
           f'com alíquotas de teste (CBS {pct(a["cbs"])}% · IBS {pct(a["ibsEstadual"] + a["ibsMunicipal"])}%). '
           'Não são alíquotas de cobrança. Sujeito a validação fiscal.</div>')
    emp = d["empresa"]
    ger = datetime.fromisoformat(d["geradoEm"]).strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Diagnóstico — {e(emp.get("nome", ""))}</title><style>
@page{{size:A4;margin:16mm}}body{{font-family:Inter,system-ui,sans-serif;color:#14201B;font-size:12px;line-height:1.5;margin:24px}}
h1{{font-size:22px;margin:4px 0 0}}h2{{font-size:14px;margin:26px 0 8px}}
.topo{{border-bottom:2px solid #0F6B4F;padding-bottom:12px;display:flex;justify-content:space-between;gap:16px}}
.eyebrow{{font-size:10px;font-weight:700;color:#0F6B4F;text-transform:uppercase;letter-spacing:.06em}}.mut{{color:#56615B;font-size:11px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px}}.kpi{{background:#F6F7F4;border-radius:8px;padding:12px}}
.kpi b{{display:block;font-size:18px;margin-top:2px}}table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:10px;text-transform:uppercase;color:#56615B;padding:6px 8px}}td{{padding:8px;border-top:1px solid #E3E6E1;vertical-align:top}}
.num{{text-align:right;white-space:nowrap}}.aviso{{border-radius:8px;padding:10px 12px;margin-top:14px;background:#FBEFD5;color:#5A3705}}
.teste{{background:#FBE3E3;color:#7A1212}}footer{{margin-top:24px;font-size:10px;color:#56615B;border-top:1px solid #E3E6E1;padding-top:10px}}
</style></head><body>
<div class="topo"><div><div class="eyebrow">{e(marca or "Diagnóstico de Impacto da Reforma")}</div><h1>{e(emp.get("nome") or "Empresa")}</h1>
<div class="mut">CNPJ {e(emp.get("cnpj", ""))} · {e(emp.get("uf", ""))}</div></div>
<div class="mut" style="text-align:right">Gerado em {ger}<br>{d["notasLidas"]} nota(s) · {d["itensTotal"]} item(ns)</div></div>
{mock}{sim}{parcial}
<div class="kpis"><div class="kpi"><span class="mut">Carga atual (ICMS, PIS, COFINS, ISS){" · itens calculados" if d.get("amostraParcial") else ""}</span><b>{brl(t["cargaAtual"])}</b></div>
<div class="kpi"><span class="mut">Carga {"calculada" if conf else "projetada"} (CBS + IBS)</span><b>{brl(t["cargaProjetada"])}</b></div>
<div class="kpi"><span class="mut">Variação{" (só na simulação)" if conf else ""}</span><b>{var}</b></div>
<div class="kpi"><span class="mut">Itens com pendência</span><b>{d["itensComPendencia"]} de {d["itensTotal"]}</b></div></div>
{div}<h2>Cadastros para corrigir</h2>
{f'<table><thead><tr><th>Item</th><th>Problema</th><th>O que fazer</th><th class="num">Vezes</th><th class="num">Valor</th></tr></thead><tbody>{linhas}</tbody></table>' if linhas else "<p>Nenhuma pendência encontrada.</p>"}
{"<h2>Avisos</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in d["avisos"][:10]) + "</ul>" if d["avisos"] else ""}
<footer>Cálculo feito com a calculadora disponibilizada pela Receita Federal (modo: {d["modoCalculadora"]}). Estimativa; não substitui a apuração oficial.</footer>
</body></html>"""
