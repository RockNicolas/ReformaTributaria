// Relatório do diagnóstico: HTML (visualização) e PDF (via Chrome/Chromium headless).
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Diagnostico } from './types.ts';

const brl = (n: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(n);

const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export function renderHtml(d: Diagnostico): string {
  const t = d.totais;
  const variacao =
    t.variacaoPercentual === null
      ? '—'
      : `${t.variacaoPercentual > 0 ? '+' : ''}${t.variacaoPercentual.toString().replace('.', ',')}%`;
  const a = d.aliquotasSimulacao;
  const mock =
    d.modoCalculadora === 'mock'
      ? `<div class="aviso teste"><strong>RESULTADO DE TESTE.</strong> Gerado por um simulador, não pela calculadora da Receita Federal. Não use com clientes.</div>`
      : '';
  const linhas = d.pendencias
    .slice(0, 60)
    .map(
      (p) => `<tr>
        <td><strong>${esc(p.descricao || p.cProd)}</strong><br><span class="mut">cód. ${esc(p.cProd)}${p.ncm ? ` · NCM ${esc(p.ncm)}` : ''}</span></td>
        <td>${esc(p.titulo)}<br><span class="mut">${esc(p.detalhe)}</span></td>
        <td>${esc(p.sugestao)}</td>
        <td class="num">${p.ocorrencias}</td>
        <td class="num">${brl(p.valorTotal)}</td>
      </tr>`,
    )
    .join('');
  return `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Diagnóstico de Impacto da Reforma — ${esc(d.empresa.nome)}</title>
<style>
  @page { size: A4; margin: 16mm; }
  body { font-family: Inter, system-ui, sans-serif; color: #14201B; font-size: 12px; line-height: 1.5; margin: 0; }
  h1 { font-size: 22px; margin: 4px 0 0; } h2 { font-size: 14px; margin: 26px 0 8px; }
  .topo { border-bottom: 2px solid #0F6B4F; padding-bottom: 12px; display: flex; justify-content: space-between; gap: 16px; }
  .eyebrow { font-size: 10px; font-weight: 700; color: #0F6B4F; text-transform: uppercase; letter-spacing: .06em; }
  .mut { color: #56615B; font-size: 11px; }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 16px; }
  .kpi { background: #F6F7F4; border-radius: 8px; padding: 12px; } .kpi b { display: block; font-size: 18px; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; } th { text-align: left; font-size: 10px; text-transform: uppercase; color: #56615B; padding: 6px 8px; }
  td { padding: 8px; border-top: 1px solid #E3E6E1; vertical-align: top; } .num { text-align: right; white-space: nowrap; }
  .aviso { border-radius: 8px; padding: 10px 12px; margin-top: 14px; background: #FBEFD5; color: #5A3705; }
  .teste { background: #FBE3E3; color: #7A1212; }
  footer { margin-top: 24px; font-size: 10px; color: #56615B; border-top: 1px solid #E3E6E1; padding-top: 10px; }
</style></head><body>
<div class="topo">
  <div><div class="eyebrow">Diagnóstico de Impacto da Reforma</div><h1>${esc(d.empresa.nome || 'Empresa')}</h1>
    <div class="mut">CNPJ ${esc(d.empresa.cnpj)} · ${esc(d.empresa.uf)}</div></div>
  <div class="mut" style="text-align:right">Gerado em ${new Date(d.geradoEm).toLocaleString('pt-BR')}<br>${d.notasLidas} ${d.notasLidas === 1 ? 'nota' : 'notas'} · ${d.itensTotal} ${d.itensTotal === 1 ? 'item' : 'itens'}</div>
</div>
${mock}
<div class="aviso"><strong>Estimativa.</strong> Simulação para fato gerador em ${esc(d.dataSimulacao.slice(0, 10))}, com alíquotas de teste
  (CBS ${a.cbs.toString().replace('.', ',')}% · IBS ${(a.ibsEstadual + a.ibsMunicipal).toString().replace('.', ',')}%).
  Não são alíquotas de cobrança. Resultado sujeito a validação fiscal.</div>
<div class="kpis">
  <div class="kpi"><span class="mut">Carga atual (ICMS, PIS, COFINS, ISS)</span><b>${brl(t.cargaAtual)}</b></div>
  <div class="kpi"><span class="mut">Carga projetada (CBS + IBS)</span><b>${brl(t.cargaProjetada)}</b></div>
  <div class="kpi"><span class="mut">Variação</span><b>${variacao}</b></div>
  <div class="kpi"><span class="mut">Itens com pendência</span><b>${d.itensComPendencia} de ${d.itensTotal}</b></div>
</div>
<h2>Detalhe da simulação</h2>
<table><tbody>
  <tr><td>Base de cálculo dos itens calculados</td><td class="num">${brl(t.baseCalculo)}</td></tr>
  <tr><td>CBS</td><td class="num">${brl(t.cbs)}</td></tr>
  <tr><td>IBS</td><td class="num">${brl(t.ibs)}</td></tr>
  <tr><td>Imposto Seletivo</td><td class="num">${brl(t.is)}</td></tr>
</tbody></table>
<h2>Cadastros para corrigir${d.pendencias.length > 60 ? ' (60 maiores)' : ''}</h2>
${
  linhas
    ? `<table><thead><tr><th>Item</th><th>Problema</th><th>O que fazer</th><th class="num">Vezes</th><th class="num">Valor</th></tr></thead><tbody>${linhas}</tbody></table>`
    : '<p>Nenhuma pendência encontrada.</p>'
}
${d.avisos.length ? `<h2>Avisos</h2><ul>${d.avisos.slice(0, 10).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
<footer>Cálculo feito com a calculadora disponibilizada pela Receita Federal (modo: ${d.modoCalculadora}). Este relatório é uma estimativa e não substitui a apuração oficial.</footer>
</body></html>`;
}

/** Converte HTML em PDF com o Chrome/Chromium instalado (CHROME_PATH ou "google-chrome"). */
export async function htmlParaPdf(html: string, saida: string): Promise<void> {
  const chrome = process.env.CHROME_PATH ?? 'google-chrome';
  const dir = await mkdtemp(join(tmpdir(), 'relatorio-'));
  const arquivo = join(dir, 'relatorio.html');
  try {
    await writeFile(arquivo, html, 'utf8');
    await new Promise<void>((ok, falha) => {
      const p = spawn(
        chrome,
        ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer', `--print-to-pdf=${saida}`, `file://${arquivo}`],
        { stdio: 'ignore' },
      );
      p.on('error', (e) => falha(new Error(`Chrome não encontrado (${chrome}): ${e.message}`)));
      p.on('exit', (c) => (c === 0 ? ok() : falha(new Error(`Chrome saiu com código ${c}`))));
    });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
