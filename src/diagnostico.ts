// Motor do diagnóstico: NF-e -> operação -> calculadora -> totais + lista de pendências.
import { createHash, randomUUID } from 'node:crypto';
import type { CalculadoraClient } from './calculadora.ts';
import type {
  AliquotasNominais,
  Diagnostico,
  ItemOperacao,
  Nfe,
  NfeItem,
  ObjetoResposta,
  Operacao,
  Pendencia,
} from './types.ts';

export interface OpcoesDiagnostico {
  /** Data do fato gerador simulado. Em 2027 a calculadora exige alíquotas nominais informadas. */
  dataSimulacao: string;
  /** Alíquotas de SIMULAÇÃO. Ajuste conforme o regulamento vigente antes de usar com cliente. */
  aliquotas: AliquotasNominais;
  concorrencia: number;
}

/** Padrão = alíquotas do exemplo da documentação da Receita (não são oficiais para cobrança). */
export const OPCOES_PADRAO: OpcoesDiagnostico = {
  dataSimulacao: '2027-03-10T10:00:00-03:00',
  aliquotas: { cbs: 8.8, ibsEstadual: 0.05, ibsMunicipal: 0.05 },
  concorrencia: 4,
};

const r2 = (n: number) => Math.round(n * 100) / 100;
const dinheiro = (s?: string) => (s ? Number(s) || 0 : 0);

function camposFaltando(i: NfeItem): string[] {
  const f: string[] = [];
  if (!i.ncm) f.push('NCM');
  if (!i.cst) f.push('CST do IBS/CBS');
  if (!i.cClassTrib) f.push('cClassTrib');
  return f;
}

function paraOperacao(nfe: Nfe, itens: NfeItem[], o: OpcoesDiagnostico): Operacao {
  return {
    id: createHash('md5').update(nfe.chave || randomUUID()).digest('hex'),
    versao: '1.0.0',
    dhFatoGerador: o.dataSimulacao,
    municipio: Number(nfe.cMunFG) || 0,
    uf: nfe.ufEmit,
    tpDoc: 55,
    itens: itens.map<ItemOperacao>((i) => ({
      numero: i.numero,
      ncm: i.ncm,
      cst: i.cst!,
      cClassTrib: i.cClassTrib!,
      baseCalculo: i.baseCalculo,
      quantidade: i.quantidade,
      unidade: i.unidade,
      aliquotasNominais: o.aliquotas,
    })),
  };
}

async function emParalelo<T>(itens: T[], limite: number, fn: (x: T) => Promise<void>) {
  let i = 0;
  const workers = Array.from({ length: Math.min(limite, itens.length) }, async () => {
    while (i < itens.length) await fn(itens[i++]);
  });
  await Promise.all(workers);
}

export async function diagnosticar(
  nfes: Nfe[],
  client: CalculadoraClient,
  opcoes: Partial<OpcoesDiagnostico> = {},
): Promise<Diagnostico> {
  const o = { ...OPCOES_PADRAO, ...opcoes };
  const pend = new Map<string, Pendencia>();
  const avisos: string[] = [];
  const t = { base: 0, cbs: 0, ibs: 0, is: 0, atual: 0 };
  let itensTotal = 0;
  let itensCalculados = 0;
  let itensComPendencia = 0;
  let notasComFalha = 0;

  const anotar = (p: Omit<Pendencia, 'ocorrencias' | 'valorTotal'>, valor: number) => {
    const k = `${p.tipo}|${p.codigo}|${p.cProd}|${p.ncm ?? ''}`;
    const atual = pend.get(k);
    if (atual) {
      atual.ocorrencias += 1;
      atual.valorTotal = r2(atual.valorTotal + valor);
    } else {
      pend.set(k, { ...p, ocorrencias: 1, valorTotal: r2(valor) });
    }
    itensComPendencia += 1;
  };

  await emParalelo(nfes, o.concorrencia, async (nfe) => {
    const porNumero = new Map(nfe.itens.map((i) => [i.numero, i]));
    const enviaveis: NfeItem[] = [];

    for (const i of nfe.itens) {
      itensTotal += 1;
      t.atual += i.vICMS + i.vPIS + i.vCOFINS + i.vISSQN;
      const falta = camposFaltando(i);
      if (falta.length) {
        anotar(
          {
            tipo: 'CADASTRO_INCOMPLETO',
            codigo: 'CAD-001',
            titulo: 'Cadastro fiscal incompleto',
            detalhe: `Faltando: ${falta.join(', ')}`,
            sugestao: 'Completar a classificação tributária do produto/serviço no ERP.',
            cProd: i.cProd,
            descricao: i.descricao,
            ncm: i.ncm,
            cClassTrib: i.cClassTrib,
          },
          i.baseCalculo,
        );
      } else {
        enviaveis.push(i);
      }
    }
    if (enviaveis.length === 0) return;

    let objetos: ObjetoResposta[];
    try {
      const resp = await client.calcularObservabilidade(paraOperacao(nfe, enviaveis, o));
      objetos = resp.objetos ?? [];
    } catch (e) {
      notasComFalha += 1;
      avisos.push(`NF-e ${nfe.numero ?? nfe.chave}: ${(e as Error).message}`);
      for (const i of enviaveis) {
        anotar(
          {
            tipo: 'FALHA_TECNICA',
            codigo: 'TEC-001',
            titulo: 'Falha ao consultar a calculadora',
            detalhe: (e as Error).message,
            sugestao: 'Repetir o diagnóstico; se persistir, verificar a calculadora.',
            cProd: i.cProd,
            descricao: i.descricao,
            ncm: i.ncm,
            cClassTrib: i.cClassTrib,
          },
          i.baseCalculo,
        );
      }
      return;
    }

    for (const obj of objetos) {
      const item = porNumero.get(obj.nObj);
      if (!item) continue;
      const g = obj.tribCalc?.IBSCBS?.gIBSCBS;
      if (obj.estadoItem === 'CALCULADO' || obj.estadoItem === 'CALCULO_SIMULADO') {
        itensCalculados += 1;
        t.base += dinheiro(g?.vBC);
        t.cbs += dinheiro(g?.gCBS?.vCBS);
        t.ibs += dinheiro(g?.vIBS);
        t.is += dinheiro(obj.tribCalc?.IS?.vIS);
        continue;
      }
      const erro = obj.erros?.[0];
      anotar(
        {
          tipo: obj.estadoItem === 'FALHA_TECNICA' ? 'FALHA_TECNICA' : 'ERRO_CALCULADORA',
          codigo: erro?.code ?? obj.estadoItem,
          titulo: erro?.title ?? obj.estadoItem,
          detalhe: erro?.detail ?? 'Item não calculado pela calculadora.',
          sugestao:
            obj.estadoItem === 'INCONSISTENCIA_ENTRADA'
              ? 'Revisar NCM/NBS e classificação (cClassTrib) do item.'
              : 'Verificar com o suporte técnico.',
          cProd: item.cProd,
          descricao: item.descricao,
          ncm: item.ncm,
          cClassTrib: item.cClassTrib,
        },
        item.baseCalculo,
      );
    }
  });

  const projetada = t.cbs + t.ibs;
  const emissor = nfes[0];
  return {
    id: randomUUID(),
    geradoEm: new Date().toISOString(),
    modoCalculadora: client.cfg.modo,
    dataSimulacao: o.dataSimulacao,
    aliquotasSimulacao: o.aliquotas,
    empresa: {
      cnpj: emissor?.emitCnpj ?? '',
      nome: emissor?.emitNome ?? '',
      uf: emissor?.ufEmit ?? '',
    },
    notasLidas: nfes.length,
    notasComFalha,
    itensTotal,
    itensCalculados,
    itensComPendencia,
    totais: {
      baseCalculo: r2(t.base),
      cbs: r2(t.cbs),
      ibs: r2(t.ibs),
      is: r2(t.is),
      cargaAtual: r2(t.atual),
      cargaProjetada: r2(projetada),
      variacaoPercentual: t.atual > 0 ? r2(((projetada - t.atual) / t.atual) * 100) : null,
    },
    pendencias: [...pend.values()].sort((a, b) => b.valorTotal - a.valorTotal),
    avisos,
  };
}
