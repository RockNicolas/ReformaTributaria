# Reforma Tributária — Diagnóstico e Validação

Serviço (Python/FastAPI) em cima da **calculadora oficial da Receita Federal** (Java, MIT, versão fixada, em Docker).
Não emite nota fiscal; só lê XMLs e valida/calcula.

## O que faz
- **Diagnóstico (simulação):** lê XMLs de NF-e/NFC-e, projeta CBS+IBS e compara com a carga atual (ICMS+PIS+COFINS+ISS).
- **Conferência:** recalcula na data da própria nota e aponta divergências do IBS/CBS declarado (`DIV-001`).
- **Lista de pendências de cadastro:** itens sem NCM/CST/cClassTrib e erros do motor (`REG-xxx`) com **o que fazer**.
- **`POST /v1/validar`:** valida uma operação e devolve erros com ação sugerida.
- X-API-Key + limite por minuto; relatório HTML imprimível (com `?marca=` para white-label simples).

## Automações
- **Planilha de produtos → cadastro fiscal pronto (principal):** `POST /api/planilha` (ou a 2ª seção da tela). CSV `codigo;descricao;ncm` entra; sai CSV com CST/cClassTrib sugeridos, conferidos no motor, com status (pronto / revisar / erro / sem NCM) e o que fazer. Exemplo: `tests/fixtures/produtos-exemplo.csv`.
- **SPED (universal, para contadores):** `POST /api/sped/cadastro-fiscal`: lê o registro 0200 (itens + NCM) do SPED Fiscal/Contribuições; funciona com qualquer ERP.
- **Omie:** `POST /api/omie/cadastro-fiscal` (ListarProdutos). **XMLs em ZIP** aceitos no diagnóstico.
- **Sienge:** `POST /api/sienge/cadastro-fiscal` busca `/bulk-data/v1/invoice-itens` (NCM, produto fiscal, CST), extrai os produtos e devolve o cadastro conferido. Só clientes Sienge em nuvem. Autenticação (Basic), URL base e nomes dos campos JSON ainda **não verificados** com credenciais reais.
- **Cadastro sugerido (CSV):** `GET /api/diagnosticos/{id}/sugestoes.csv` ou `POST /v1/sugerir-classificacao`. Para cada NCM, consulta o motor
  e lista a classificação vinculada por lei (`REVISAR`) ou o padrão (`PADRAO_PROVAVEL`). O motor não decide a classificação: o contador confirma.
- **Validar antes de emitir:** `POST /v1/validar-nfe` (XML) e `POST /v1/validar` (operação JSON).
- **Monitor de pasta:** `docker compose --profile monitor up` processa os XMLs novos de `./dados/entrada`, gera relatório + CSV em
  `./dados/saida` e, com `--webhook URL`, avisa quando há problema novo.

## Rodar (Docker)
```bash
docker compose up --build        # 1ª vez demora: baixa o motor, gera o banco e compila
# abra http://localhost:8000   (UI)   ·   http://localhost:8000/docs   (API)
API_KEYS=minha-chave docker compose up   # exige X-API-Key
```
Sem Docker, para testar o fluxo com o **simulador** (resultado NÃO vale):
```bash
pip install -r requirements-dev.txt
pytest
MODO_CALCULADORA=mock uvicorn app.main:app --reload
```

## Atenção (antes de vender)
- Alíquotas de simulação (CBS 8,8 / IBS 0,05+0,05) vêm do exemplo da documentação, **não são de cobrança**. Valide com a consultoria fiscal.
- Layout do grupo `IBSCBS` da NF-e assumido (`det/imposto/IBSCBS/gIBSCBS/...`): conferir com uma NF-e real.
- Motor fixado em 1.6.1 (Java 21). A 1.7.x muda arredondamentos de centavos; trocar via `ENGINE_REF`/`JDK_VERSION`.
- Resultados ficam em memória (200 últimos); em produção, trocar por banco.

`prototipo-ts/` é o protótipo anterior em TypeScript (referência).
