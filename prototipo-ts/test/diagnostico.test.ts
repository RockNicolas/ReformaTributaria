import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, before, describe, it } from 'node:test';
import type { Server } from 'node:http';
import { CalculadoraClient } from '../src/calculadora.ts';
import { diagnosticar } from '../src/diagnostico.ts';
import { iniciarMock } from '../src/mock.ts';
import { lerNfe, NfeInvalidaError } from '../src/nfe.ts';
import { renderHtml } from '../src/relatorio.ts';

const PORTA = 18081;
const xml = await readFile(new URL('./fixtures/nfe-exemplo.xml', import.meta.url), 'utf8');
let mock: Server;

before(async () => {
  mock = await iniciarMock(PORTA);
});
after(() => mock.close());

const clienteMock = () =>
  new CalculadoraClient({ baseUrl: `http://localhost:${PORTA}/api`, modo: 'mock' });

describe('lerNfe', () => {
  it('extrai emitente, município e itens', () => {
    const n = lerNfe(xml);
    assert.equal(n.emitNome, 'Comércio Modelo S/A');
    assert.equal(n.cMunFG, '3550308');
    assert.equal(n.ufEmit, 'SP');
    assert.equal(n.itens.length, 4);
    assert.equal(n.itens[1].cClassTrib, '200028');
    assert.equal(n.itens[1].vICMS, 360);
    assert.equal(n.itens[2].cClassTrib, undefined);
  });

  it('rejeita XML que não é NF-e', () => {
    assert.throws(() => lerNfe('<a><b/></a>'), NfeInvalidaError);
  });
});

describe('diagnosticar', () => {
  it('calcula os itens válidos e lista as pendências', async () => {
    const d = await diagnosticar([lerNfe(xml)], clienteMock());
    assert.equal(d.itensTotal, 4);
    assert.equal(d.itensCalculados, 2);
    assert.equal(d.itensComPendencia, 2);
    assert.deepEqual(d.pendencias.map((p) => p.codigo).sort(), ['CAD-001', 'REG-011']);
    // item 1: sem redução; item 2: redução de teste de 60%
    assert.equal(d.totais.baseCalculo, 3000);
    assert.equal(d.totais.cbs, 158.4);
    assert.equal(d.totais.ibs, 1.8);
    assert.equal(d.totais.cargaAtual, 817.5);
    assert.equal(d.totais.cargaProjetada, 160.2);
    assert.equal(d.modoCalculadora, 'mock');
  });

  it('marca falha técnica quando a calculadora está fora do ar', async () => {
    const fora = new CalculadoraClient({ baseUrl: 'http://localhost:1/api', modo: 'oficial', timeoutMs: 1500 });
    const d = await diagnosticar([lerNfe(xml)], fora);
    assert.equal(d.notasComFalha, 1);
    assert.equal(d.itensCalculados, 0);
    assert.ok(d.pendencias.some((p) => p.tipo === 'FALHA_TECNICA'));
    assert.equal(d.avisos.length, 1);
  });
});

describe('relatório', () => {
  it('avisa quando o resultado veio do simulador de teste', async () => {
    const d = await diagnosticar([lerNfe(xml)], clienteMock());
    const html = renderHtml(d);
    assert.match(html, /RESULTADO DE TESTE/);
    assert.match(html, /Cimento|Item com NCM inconsistente/);
    assert.match(html, /Estimativa/);
  });

  it('escapa HTML vindo do XML', async () => {
    const malicioso = xml.replace('Comércio Modelo S/A', '<script>alert(1)</script>');
    const d = await diagnosticar([lerNfe(malicioso)], clienteMock());
    assert.doesNotMatch(renderHtml(d), /<script>alert/);
  });
});
