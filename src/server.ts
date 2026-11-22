// API do diagnóstico.
//   POST /api/diagnosticos            (multipart: um ou mais arquivos .xml de NF-e)
//   GET  /api/diagnosticos/:id        (JSON do resultado)
//   GET  /api/diagnosticos/:id/relatorio.html | relatorio.pdf
// ATENÇÃO: sem autenticação. Não exponha na internet antes de colocar login e limites por cliente.
import multipart from '@fastify/multipart';
import Fastify from 'fastify';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { CalculadoraClient } from './calculadora.ts';
import { diagnosticar } from './diagnostico.ts';
import { lerNfe, NfeInvalidaError } from './nfe.ts';
import { htmlParaPdf, renderHtml } from './relatorio.ts';
import type { Diagnostico, Nfe } from './types.ts';

const DATA = process.env.DATA_DIR ?? join(process.cwd(), 'data');

export function criarServidor(client: CalculadoraClient) {
  const app = Fastify({ logger: true });
  app.register(multipart, { limits: { files: 500, fileSize: 5 * 1024 * 1024 } });

  const salvar = (d: Diagnostico) => writeFile(join(DATA, `${d.id}.json`), JSON.stringify(d));
  const carregar = async (id: string): Promise<Diagnostico | null> => {
    if (!/^[0-9a-f-]{36}$/.test(id)) return null;
    try {
      return JSON.parse(await readFile(join(DATA, `${id}.json`), 'utf8')) as Diagnostico;
    } catch {
      return null;
    }
  };

  app.get('/api/saude', async () => ({ ok: true, calculadora: client.cfg.modo }));

  app.post('/api/diagnosticos', async (req, reply) => {
    const nfes: Nfe[] = [];
    const ignorados: string[] = [];
    for await (const parte of req.files()) {
      const texto = (await parte.toBuffer()).toString('utf8');
      try {
        nfes.push(lerNfe(texto));
      } catch (e) {
        if (e instanceof NfeInvalidaError) ignorados.push(`${parte.filename}: ${e.message}`);
        else throw e;
      }
    }
    if (nfes.length === 0) {
      return reply.code(400).send({ erro: 'Nenhuma NF-e válida enviada.', ignorados });
    }
    const d = await diagnosticar(nfes, client);
    d.avisos.push(...ignorados.map((x) => `Arquivo ignorado — ${x}`));
    await salvar(d);
    return reply.code(201).send(d);
  });

  app.get<{ Params: { id: string } }>('/api/diagnosticos/:id', async (req, reply) => {
    const d = await carregar(req.params.id);
    return d ?? reply.code(404).send({ erro: 'Diagnóstico não encontrado.' });
  });

  app.get<{ Params: { id: string } }>('/api/diagnosticos/:id/relatorio.html', async (req, reply) => {
    const d = await carregar(req.params.id);
    if (!d) return reply.code(404).send({ erro: 'Diagnóstico não encontrado.' });
    return reply.type('text/html; charset=utf-8').send(renderHtml(d));
  });

  app.get<{ Params: { id: string } }>('/api/diagnosticos/:id/relatorio.pdf', async (req, reply) => {
    const d = await carregar(req.params.id);
    if (!d) return reply.code(404).send({ erro: 'Diagnóstico não encontrado.' });
    const saida = join(DATA, `${d.id}.pdf`);
    await htmlParaPdf(renderHtml(d), saida);
    return reply.type('application/pdf').send(await readFile(saida));
  });

  return app;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await mkdir(DATA, { recursive: true });
  const client = new CalculadoraClient({
    baseUrl: process.env.CALCULADORA_URL ?? 'http://localhost:8080/api',
    modo: process.env.CALCULADORA_MODO === 'mock' ? 'mock' : 'oficial',
  });
  const app = criarServidor(client);
  await app.listen({ port: Number(process.env.PORT ?? 3000), host: '0.0.0.0' });
}
