// SIMULADOR DE TESTE da calculadora. NÃO usa as regras reais: serve só para desenvolver e
// testar o fluxo sem o Java 25. Todo resultado vindo dele sai marcado como "mock" nos relatórios.
import { createServer, type Server } from 'node:http';
import type { ItemOperacao, ObjetoResposta, Operacao } from './types.ts';

// Reduções fictícias por cClassTrib, só para os testes.
const REDUCAO: Record<string, number> = { '200003': 100, '200028': 60 };

function calcularItem(i: ItemOperacao): ObjetoResposta {
  if (!i.ncm && !i.nbs) {
    return {
      nObj: i.numero,
      estadoItem: 'INCONSISTENCIA_ENTRADA',
      erros: [{ code: 'MOCK-001', title: 'NCM/NBS ausente', detail: 'Informe NCM ou NBS.' }],
    };
  }
  // Regra de teste: NCM iniciando em 99 simula "NCM não vinculada à cClassTrib".
  if (i.ncm?.startsWith('99')) {
    return {
      nObj: i.numero,
      estadoItem: 'INCONSISTENCIA_ENTRADA',
      erros: [
        {
          code: 'REG-011',
          title: 'NCM não vinculada',
          pointer: `#/itens/${i.numero - 1}/ncm`,
          detail: `NCM de código ${i.ncm} não vinculada à Classificação Tributária de código ${i.cClassTrib} (CBS e IBS)`,
        },
      ],
    };
  }
  const fator = 1 - (REDUCAO[i.cClassTrib] ?? 0) / 100;
  const a = i.aliquotasNominais ?? { cbs: 0, ibsEstadual: 0, ibsMunicipal: 0 };
  const vCBS = (i.baseCalculo * fator * a.cbs) / 100;
  const vIBS = (i.baseCalculo * fator * (a.ibsEstadual + a.ibsMunicipal)) / 100;
  return {
    nObj: i.numero,
    estadoItem: 'CALCULO_SIMULADO',
    tribCalc: {
      IBSCBS: {
        gIBSCBS: {
          vBC: i.baseCalculo.toFixed(2),
          vIBS: vIBS.toFixed(2),
          gCBS: { vCBS: vCBS.toFixed(2) },
        },
      },
    },
  };
}

export function iniciarMock(porta = 8080): Promise<Server> {
  const srv = createServer((req, res) => {
    const json = (status: number, corpo: unknown) => {
      res.writeHead(status, { 'Content-Type': 'application/json', 'x-mock': 'true' });
      res.end(JSON.stringify(corpo));
    };
    if (req.method === 'GET' && req.url === '/api/versao') {
      return json(200, { aplicacao: 'mock', base: 'mock', ambiente: 'teste' });
    }
    if (req.method === 'POST' && req.url === '/api/calculadora/observabilidade/regime-geral') {
      let corpo = '';
      req.on('data', (c) => (corpo += c));
      req.on('end', () => {
        try {
          const op = JSON.parse(corpo) as Operacao;
          if (!op.itens?.length) return json(422, { erro: 'itens obrigatórios' });
          return json(200, { objetos: op.itens.map(calcularItem) });
        } catch {
          return json(400, { erro: 'JSON inválido' });
        }
      });
      return;
    }
    json(404, { erro: 'rota não existe no mock' });
  });
  return new Promise((ok) => srv.listen(porta, () => ok(srv)));
}

// `npm run mock` sobe o simulador na porta 8080 (a mesma da calculadora oficial).
if (import.meta.url === `file://${process.argv[1]}`) {
  const porta = Number(process.env.PORT ?? 8080);
  iniciarMock(porta).then(() => console.log(`Mock da calculadora em http://localhost:${porta}/api (TESTE)`));
}
