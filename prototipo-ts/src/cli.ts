// Uso: npm run cli -- <pasta-com-xmls> [--mock] [--url http://localhost:8080/api] [--out ./saida]
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { CalculadoraClient } from './calculadora.ts';
import { diagnosticar } from './diagnostico.ts';
import { iniciarMock } from './mock.ts';
import { lerNfe, NfeInvalidaError } from './nfe.ts';
import { htmlParaPdf, renderHtml } from './relatorio.ts';

const args = process.argv.slice(2);
const flag = (nome: string) => args.includes(nome);
const valor = (nome: string) => {
  const i = args.indexOf(nome);
  return i >= 0 ? args[i + 1] : undefined;
};
const pasta = args.find((a) => !a.startsWith('--') && a !== valor('--url') && a !== valor('--out'));
if (!pasta) {
  console.error('Uso: npm run cli -- <pasta-com-xmls> [--mock] [--url <api>] [--out <pasta>]');
  process.exit(1);
}

const usarMock = flag('--mock');
const porta = 18080;
const servidor = usarMock ? await iniciarMock(porta) : undefined;
const client = new CalculadoraClient({
  baseUrl: usarMock ? `http://localhost:${porta}/api` : (valor('--url') ?? 'http://localhost:8080/api'),
  modo: usarMock ? 'mock' : 'oficial',
});

const dir = resolve(pasta);
const nfes = [];
for (const nome of (await readdir(dir)).filter((n) => n.toLowerCase().endsWith('.xml'))) {
  try {
    nfes.push(lerNfe(await readFile(join(dir, nome), 'utf8')));
  } catch (e) {
    if (e instanceof NfeInvalidaError) console.warn(`Ignorado ${nome}: ${e.message}`);
    else throw e;
  }
}
console.log(`${nfes.length} NF-e lidas. Calculando...`);

const d = await diagnosticar(nfes, client);
const saida = resolve(valor('--out') ?? './saida');
await mkdir(saida, { recursive: true });
await writeFile(join(saida, 'diagnostico.json'), JSON.stringify(d, null, 2));
const html = renderHtml(d);
await writeFile(join(saida, 'relatorio.html'), html);
try {
  await htmlParaPdf(html, join(saida, 'relatorio.pdf'));
} catch (e) {
  console.warn(`PDF não gerado: ${(e as Error).message}`);
}
servidor?.close();
console.log(
  `Pronto: ${d.itensCalculados}/${d.itensTotal} itens calculados, ${d.pendencias.length} pendências. Arquivos em ${saida}`,
);
