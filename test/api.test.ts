import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile } from 'node:fs/promises';
import type { Server } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, describe, it } from 'node:test';

// DATA_DIR é lido na importação do servidor, então precisa ser definido antes.
process.env.DATA_DIR = await mkdtemp(join(tmpdir(), 'dados-'));
const { criarServidor } = await import('../src/server.ts');
const { CalculadoraClient } = await import('../src/calculadora.ts');
const { iniciarMock } = await import('../src/mock.ts');

const xml = await readFile(new URL('./fixtures/nfe-exemplo.xml', import.meta.url), 'utf8');
let mock: Server;
let app: ReturnType<typeof criarServidor>;
let base: string;

before(async () => {
  mock = await iniciarMock(18083);
  app = criarServidor(new CalculadoraClient({ baseUrl: 'http://localhost:18083/api', modo: 'mock' }));
  base = await app.listen({ port: 0, host: '127.0.0.1' });
});
after(async () => {
  await app.close();
  mock.close();
});

const enviar = (conteudo: string, nome = 'nota.xml') => {
  const f = new FormData();
  f.append('arquivo', new Blob([conteudo], { type: 'application/xml' }), nome);
  return fetch(`${base}/api/diagnosticos`, { method: 'POST', body: f });
};

describe('API', () => {
  it('recebe um XML, calcula e devolve o diagnóstico', async () => {
    const res = await enviar(xml);
    assert.equal(res.status, 201);
    const d = (await res.json()) as any;
    assert.equal(d.itensTotal, 4);
    assert.equal(d.itensCalculados, 2);
    assert.equal(d.modoCalculadora, 'mock');

    const again = await fetch(`${base}/api/diagnosticos/${d.id}`);
    assert.equal(again.status, 200);
    const html = await fetch(`${base}/api/diagnosticos/${d.id}/relatorio.html`);
    assert.match(await html.text(), /RESULTADO DE TESTE/);
  });

  it('gera o PDF do relatório', { skip: !existsSync('/usr/bin/google-chrome') }, async () => {
    const d = (await (await enviar(xml)).json()) as any;
    const pdf = await fetch(`${base}/api/diagnosticos/${d.id}/relatorio.pdf`);
    assert.equal(pdf.status, 200);
    assert.equal(Buffer.from(await pdf.arrayBuffer()).subarray(0, 4).toString(), '%PDF');
  });

  it('recusa arquivo que não é NF-e', async () => {
    const res = await enviar('{"a":1}', 'x.json');
    assert.equal(res.status, 400);
    const corpo = (await res.json()) as any;
    assert.equal(corpo.ignorados.length, 1);
  });

  it('não aceita id fora do formato (sem acesso a outros arquivos)', async () => {
    const res = await fetch(`${base}/api/diagnosticos/..%2F..%2Fetc%2Fpasswd`);
    assert.equal(res.status, 404);
    const res2 = await fetch(`${base}/api/diagnosticos/nao-existe`);
    assert.equal(res2.status, 404);
  });
});
