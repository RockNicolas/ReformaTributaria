# Diagnóstico de Impacto da Reforma

Lê XMLs de NF-e, manda cada nota para a **calculadora oficial da Receita Federal**
(`calculadora-rtc-regime-regular`, licença MIT) e entrega:

- carga atual (ICMS + PIS + COFINS + ISS declarados na nota) x carga projetada (CBS + IBS);
- lista de cadastros para corrigir (sem CST/cClassTrib, NCM não vinculada etc.);
- relatório em HTML e PDF.

## Estado atual

| Parte | Situação |
|---|---|
| Leitura de NF-e (`src/nfe.ts`) | Pronta, testada com uma NF-e **fictícia** |
| Cliente da calculadora (`src/calculadora.ts`) | Pronto, segue o contrato da doc da Receita (`/observabilidade/regime-geral`) |
| Motor do diagnóstico, relatório HTML/PDF, API | Prontos, 10 testes passando |
| Teste contra a calculadora **real** | **Ainda não feito** (precisa de Java 25, ver abaixo) |
| Login, multiempresa, cobrança, tela web | Não feitos |

Os testes usam um **simulador** (`src/mock.ts`) com regras inventadas. Todo relatório gerado
com ele sai com a faixa vermelha "RESULTADO DE TESTE". Nunca entregue esse relatório a cliente.

## Rodar a calculadora oficial (Windows, uma vez)

Requisitos: Java 25, Git e internet.

```bat
git clone https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git
cd calculadora-rtc-regime-regular
mkdir calculadora\db
mvnw.cmd flyway:migrate -Dflyway.configFiles=flyway\flyway-pro.conf --batch-mode --errors
mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=offline"
```

A API sobe em `http://localhost:8080/api` (Swagger em `/api/swagger-ui.html`).

## Rodar este projeto

```bash
npm install
npm test                                   # testes (usam o simulador)
npm run cli -- ./pasta-com-xmls            # usa a calculadora em localhost:8080
npm run cli -- ./pasta-com-xmls --mock     # usa o simulador (só para teste)
npm start                                  # API na porta 3000
```

Variáveis: `CALCULADORA_URL` (padrão `http://localhost:8080/api`), `CALCULADORA_MODO=mock`,
`PORT`, `DATA_DIR`, `CHROME_PATH` (para o PDF).

API: `POST /api/diagnosticos` (multipart, campo com um ou mais `.xml`),
`GET /api/diagnosticos/:id`, `GET /api/diagnosticos/:id/relatorio.html|pdf`.

## Antes de usar com cliente

1. Rodar contra a calculadora real e conferir um resultado com a NID.
2. Confirmar os campos do grupo `IBSCBS` no leiaute da NF-e (o leitor assume `det/imposto/IBSCBS/CST` e `cClassTrib`).
3. Definir as alíquotas de simulação (`OPCOES_PADRAO` em `src/diagnostico.ts`). Os valores atuais vêm
   do exemplo da documentação da Receita e não são alíquotas de cobrança.
4. Colocar autenticação na API (hoje não tem) e limites por cliente.
5. Base de cálculo: hoje é `vProd + frete + seguro + outras - desconto`. A calculadora tem o endpoint
   `/base-calculo/base-calculo-unificada` para o valor exato.
