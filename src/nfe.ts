// Leitura de XML de NF-e (modelo 55) e NFC-e (65): extrai o que o diagnóstico precisa.
import { XMLParser } from 'fast-xml-parser';
import type { Nfe, NfeItem } from './types.ts';

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  parseTagValue: false, // mantém tudo como texto (NCM e CST têm zeros à esquerda)
  isArray: (name) => name === 'det',
});

const num = (v: unknown): number => {
  if (v === undefined || v === null || v === '') return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const str = (v: unknown): string | undefined =>
  v === undefined || v === null || v === '' ? undefined : String(v);

/** Busca em profundidade o primeiro valor de uma tag (ex.: vICMS dentro de ICMS00/ICMS20...). */
function achar(obj: unknown, chave: string): unknown {
  if (!obj || typeof obj !== 'object') return undefined;
  const o = obj as Record<string, unknown>;
  if (chave in o) return o[chave];
  for (const k of Object.keys(o)) {
    const r = achar(o[k], chave);
    if (r !== undefined) return r;
  }
  return undefined;
}

export class NfeInvalidaError extends Error {}

export function lerNfe(xml: string): Nfe {
  let doc: any;
  try {
    doc = parser.parse(xml);
  } catch {
    throw new NfeInvalidaError('Arquivo não é um XML válido.');
  }
  const inf = doc?.nfeProc?.NFe?.infNFe ?? doc?.NFe?.infNFe;
  if (!inf) throw new NfeInvalidaError('XML não contém uma NF-e/NFC-e (infNFe não encontrado).');

  const ide = inf.ide ?? {};
  const emit = inf.emit ?? {};
  const dets: any[] = inf.det ?? [];

  const itens: NfeItem[] = dets.map((d, i) => {
    const prod = d.prod ?? {};
    const imp = d.imposto ?? {};
    const vProd = num(prod.vProd);
    const base = Math.max(
      0,
      vProd + num(prod.vFrete) + num(prod.vSeg) + num(prod.vOutro) - num(prod.vDesc),
    );
    const ibscbs = imp.IBSCBS;
    return {
      numero: num(d['@_nItem']) || i + 1,
      cProd: str(prod.cProd) ?? `item-${i + 1}`,
      descricao: str(prod.xProd) ?? '',
      ncm: str(prod.NCM),
      cfop: str(prod.CFOP),
      unidade: str(prod.uCom),
      quantidade: prod.qCom !== undefined ? num(prod.qCom) : undefined,
      vProd,
      baseCalculo: Math.round(base * 100) / 100,
      cst: str(ibscbs?.CST),
      cClassTrib: str(ibscbs?.cClassTrib),
      vICMS: num(achar(imp.ICMS, 'vICMS')),
      vPIS: num(achar(imp.PIS, 'vPIS')),
      vCOFINS: num(achar(imp.COFINS, 'vCOFINS')),
      vISSQN: num(achar(imp.ISSQN, 'vISSQN')),
    };
  });

  if (itens.length === 0) throw new NfeInvalidaError('NF-e sem itens (det).');

  const id = String(inf['@_Id'] ?? '');
  return {
    chave: id.replace(/^NFe/, ''),
    numero: str(ide.nNF),
    dhEmi: str(ide.dhEmi) ?? str(ide.dEmi) ?? '',
    cMunFG: str(ide.cMunFG) ?? '',
    ufEmit: str(emit.enderEmit?.UF) ?? '',
    emitCnpj: str(emit.CNPJ) ?? str(emit.CPF) ?? '',
    emitNome: str(emit.xNome) ?? '',
    crt: str(emit.CRT),
    itens,
  };
}
