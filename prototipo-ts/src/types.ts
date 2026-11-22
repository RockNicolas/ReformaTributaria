// Tipos compartilhados do diagnóstico.

export interface NfeItem {
  numero: number;
  cProd: string;
  descricao: string;
  ncm?: string;
  cfop?: string;
  unidade?: string;
  quantidade?: number;
  vProd: number;
  /** vProd + frete + seguro + outras - desconto */
  baseCalculo: number;
  /** Grupo IBSCBS do XML (quando a nota já traz). */
  cst?: string;
  cClassTrib?: string;
  /** Tributos atuais declarados na nota, para comparar com o cenário projetado. */
  vICMS: number;
  vPIS: number;
  vCOFINS: number;
  vISSQN: number;
}

export interface Nfe {
  chave: string;
  numero?: string;
  dhEmi: string;
  cMunFG: string;
  ufEmit: string;
  emitCnpj: string;
  emitNome: string;
  crt?: string;
  itens: NfeItem[];
}

// ---- Contrato da API da calculadora (POST /observabilidade/regime-geral) ----

export interface AliquotasNominais {
  cbs: number;
  ibsEstadual: number;
  ibsMunicipal: number;
}

export interface ItemOperacao {
  numero: number;
  ncm?: string;
  nbs?: string;
  cst: string;
  cClassTrib: string;
  baseCalculo: number;
  quantidade?: number;
  unidade?: string;
  aliquotasNominais?: AliquotasNominais;
}

export interface Operacao {
  id: string;
  versao: string;
  dhFatoGerador: string;
  municipio: number;
  uf: string;
  tpDoc?: number;
  itens: ItemOperacao[];
}

export type EstadoItem =
  | 'CALCULADO'
  | 'CALCULO_SIMULADO'
  | 'INCONSISTENCIA_ENTRADA'
  | 'NAO_IMPLEMENTADO'
  | 'FALHA_TECNICA';

export interface ErroCalculadora {
  code: string;
  title: string;
  pointer?: string;
  detail?: string;
}

export interface ObjetoResposta {
  nObj: number;
  estadoItem: EstadoItem;
  erros?: ErroCalculadora[];
  tribCalc?: {
    IS?: { vIS?: string };
    IBSCBS?: {
      gIBSCBS?: {
        vBC?: string;
        vIBS?: string;
        gCBS?: { vCBS?: string };
      };
    };
  };
}

export interface RespostaObservabilidade {
  objetos: ObjetoResposta[];
}

// ---- Resultado do diagnóstico ----

export type TipoPendencia = 'CADASTRO_INCOMPLETO' | 'ERRO_CALCULADORA' | 'FALHA_TECNICA';

export interface Pendencia {
  tipo: TipoPendencia;
  codigo: string;
  titulo: string;
  detalhe: string;
  sugestao: string;
  cProd: string;
  descricao: string;
  ncm?: string;
  cClassTrib?: string;
  ocorrencias: number;
  valorTotal: number;
}

export interface Diagnostico {
  id: string;
  geradoEm: string;
  /** "oficial" = calculadora da Receita; "mock" = simulador de teste (resultado NÃO vale). */
  modoCalculadora: 'oficial' | 'mock';
  dataSimulacao: string;
  aliquotasSimulacao: AliquotasNominais;
  empresa: { cnpj: string; nome: string; uf: string };
  notasLidas: number;
  notasComFalha: number;
  itensTotal: number;
  itensCalculados: number;
  itensComPendencia: number;
  totais: {
    baseCalculo: number;
    cbs: number;
    ibs: number;
    is: number;
    cargaAtual: number;
    cargaProjetada: number;
    variacaoPercentual: number | null;
  };
  pendencias: Pendencia[];
  avisos: string[];
}
