// Cliente da API da calculadora oficial (calculadora-rtc-regime-regular, da Receita Federal).
// Base padrão do componente local: http://localhost:8080/api
import type { Operacao, RespostaObservabilidade } from './types.ts';

export interface CalculadoraConfig {
  baseUrl: string;
  /** "mock" liga o aviso de simulação de teste nos relatórios. */
  modo: 'oficial' | 'mock';
  timeoutMs?: number;
}

export class CalculadoraError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

export class CalculadoraClient {
  constructor(readonly cfg: CalculadoraConfig) {}

  private url(path: string) {
    return `${this.cfg.baseUrl.replace(/\/$/, '')}/calculadora${path}`;
  }

  /** Cálculo com observabilidade: erros por item, sem derrubar a operação inteira. */
  async calcularObservabilidade(op: Operacao): Promise<RespostaObservabilidade> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.cfg.timeoutMs ?? 30_000);
    try {
      const res = await fetch(this.url('/observabilidade/regime-geral'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(op),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const corpo = (await res.text()).slice(0, 500);
        throw new CalculadoraError(`Calculadora respondeu HTTP ${res.status}: ${corpo}`, res.status);
      }
      return (await res.json()) as RespostaObservabilidade;
    } catch (e) {
      if (e instanceof CalculadoraError) throw e;
      throw new CalculadoraError(
        `Não foi possível falar com a calculadora em ${this.cfg.baseUrl}: ${(e as Error).message}`,
      );
    } finally {
      clearTimeout(timer);
    }
  }

  /** Versão da aplicação e da base de dados (útil para registrar no relatório). */
  async versao(): Promise<unknown> {
    const res = await fetch(`${this.cfg.baseUrl.replace(/\/$/, '')}/versao`);
    if (!res.ok) throw new CalculadoraError(`HTTP ${res.status} em /versao`, res.status);
    return res.json();
  }
}
