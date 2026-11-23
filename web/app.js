"use strict";
/* Reforma Fiscal: interface. Sem dependências, sem build. Todo texto vindo de dados entra via textContent. */

const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) el.append(f.nodeType ? f : document.createTextNode(String(f)));
  return el;
}

/* ---------- armazenamento local (nada disso vai para o servidor) ---------- */
const Guarda = {
  ler(chave, padrao) {
    for (const st of [sessionStorage, localStorage]) {
      try { const v = st.getItem(chave); if (v) return JSON.parse(v); } catch { /* storage indisponível */ }
    }
    return padrao;
  },
  gravar(chave, valor, lembrar) {
    try { sessionStorage.removeItem(chave); localStorage.removeItem(chave); (lembrar ? localStorage : sessionStorage).setItem(chave, JSON.stringify(valor)); } catch { /* ignora */ }
  },
  apagar(chave) { try { sessionStorage.removeItem(chave); localStorage.removeItem(chave); } catch { /* ignora */ } },
};

const estado = { catalogo: null, origem: null, passo: 1, resultado: null, filtro: "todos", busca: "", visiveis: 100, aberta: null, erro: null, executando: false };

/* ---------- API ---------- */
async function api(caminho, opcoes = {}) {
  const chave = Guarda.ler("rf.apikey", "");
  const r = await fetch(caminho, { ...opcoes, headers: { ...(chave ? { "X-API-Key": chave } : {}), ...(opcoes.headers || {}) } });
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try { const d = await r.json(); msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail || d); } catch { /* corpo não-JSON */ }
    if (r.status === 401) msg = "Chave de acesso ausente ou inválida. Informe a chave em Ajustes.";
    throw new Error(msg);
  }
  return r;
}

/* ---------- categorias de situação ---------- */
function categoria(l) {
  if (l.status === "SEM_NCM") return "sem";
  if (l.validacao_motor === "OK") return l.status === "PADRAO_PROVAVEL" ? "pronto" : "revisar";
  return "erro";
}
const ROTULO = { pronto: ["ok", "Pronto"], revisar: ["rev", "Revisar"], erro: ["err", "Erro"], sem: ["sem", "Sem NCM"] };
const FILTROS = [["todos", "Todos"], ["pronto", "Prontos"], ["revisar", "Para revisar"], ["erro", "Com erro"], ["sem", "Sem NCM"]];

/* ---------- exportação ---------- */
const COLUNAS = ["codigo", "descricao", "ncm", "cst", "cclasstrib", "descricao_classificacao", "status", "validacao_motor", "problema", "o_que_fazer"];
function baixar(blob, nome) { const a = h("a", { href: URL.createObjectURL(blob), download: nome }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
function csvDe(linhas) {
  const esc = v => { v = String(v ?? ""); return /[;"\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v; };
  return "﻿" + [COLUNAS.join(";"), ...linhas.map(l => COLUNAS.map(c => esc(l[c])).join(";"))].join("\r\n");
}
function linhasFiltradas() {
  const q = estado.busca.trim().toLowerCase();
  return estado.resultado.linhas.filter(l => (estado.filtro === "todos" || categoria(l) === estado.filtro) &&
    (!q || [l.codigo, l.descricao, l.ncm, l.cclasstrib].some(v => String(v || "").toLowerCase().includes(q))));
}
async function exportar(tipo) {
  const linhas = linhasFiltradas();
  const nome = `cadastro-fiscal-${estado.resultado.conector}`;
  if (tipo === "csv") baixar(new Blob([csvDe(linhas)], { type: "text/csv;charset=utf-8" }), `${nome}.csv`);
  else if (tipo === "json") baixar(new Blob([JSON.stringify(linhas, null, 2)], { type: "application/json" }), `${nome}.json`);
  else if (tipo === "copiar") await navigator.clipboard.writeText([COLUNAS.join("\t"), ...linhas.map(l => COLUNAS.map(c => String(l[c] ?? "").replace(/\s+/g, " ")).join("\t"))].join("\n"));
  else if (tipo === "xlsx") {
    const r = await api("/api/exportar.xlsx", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ linhas }) });
    baixar(await r.blob(), `${nome}.xlsx`);
  }
}

/* ---------- vistas ---------- */
const vista = () => $("#vista");
function montar(...nos) { vista().replaceChildren(...nos); vista().focus({ preventScroll: true }); window.scrollTo(0, 0); }

function cabecalho(titulo, texto, ...extra) {
  return h("div", { class: "topo" }, h("div", {}, h("h1", {}, titulo), texto && h("p", {}, texto)), h("div", { class: "acoes" }, extra));
}

function credenciais(id) { return Guarda.ler(`rf.cred.${id}`, null); }
function configurada(c) { return c.campos.every(f => f.tipo === "arquivo") ? null : !!credenciais(c.id); }

/* Novo trabalho ------------------------------------------------ */
function vistaNovo() {
  if (!estado.catalogo) return carregarCatalogo().then(vistaNovo);
  const passos = ["Origem", "Parâmetros", "Resultado"];
  const trilha = h("ol", { class: "passos", "aria-label": "Etapas" }, passos.map((p, i) => h("li", {
    class: i + 1 < estado.passo ? "feito" : "", "aria-current": i + 1 === estado.passo ? "step" : false,
  }, h("span", { class: "n" }, i + 1), p)));

  if (estado.passo === 3 && estado.executando) return montar(cabecalho("Novo trabalho"), trilha, execucao());
  if (estado.passo === 3 && estado.resultado) return montar(cabecalho("Cadastro fiscal conferido", `Origem: ${nomeOrigem(estado.resultado.conector)} · ${new Date(estado.resultado.geradoEm).toLocaleString("pt-BR")}`,
    h("button", { class: "btn", onclick: () => { estado.passo = 1; estado.resultado = null; vistaNovo(); } }, "Novo trabalho")), trilha, resultado());
  if (estado.passo === 2 && estado.origem) return montar(cabecalho("Novo trabalho", "Informe os dados da origem escolhida."), trilha, formParametros());

  estado.passo = 1;
  const grupos = [...new Set(estado.catalogo.conexoes.map(c => c.grupo))];
  const lista = h("div", { class: "lista", role: "radiogroup", "aria-label": "Origem dos produtos" });
  for (const g of grupos) {
    lista.append(h("div", { class: "grupo" }, g === "Arquivo" ? "Enviar um arquivo" : "Buscar direto do sistema"));
    for (const c of estado.catalogo.conexoes.filter(x => x.grupo === g)) {
      const cfg = configurada(c);
      const sel = estado.origem?.id === c.id;
      const escolher = () => { estado.origem = c; vistaNovo(); };
      lista.append(h("div", { class: "opcao", role: "radio", "aria-checked": String(sel), tabindex: "0", onclick: escolher,
        onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escolher(); } },
        style: "display:grid;grid-template-columns:28px 1fr auto auto;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--linha)" },
        h("span", { class: "radio" }), h("div", {}, h("div", { class: "nome", style: "font-weight:600" }, c.nome), h("div", { class: "desc", style: "color:var(--tinta-2);font-size:.9rem" }, c.descricao)),
        cfg === null ? h("span", { class: "selo" }, c.formato) : h("span", { class: cfg ? "selo ok" : "selo" }, cfg ? "Credenciais salvas" : "Sem credenciais"),
        h("span", { class: c.verificacao === "Confirmar no 1º uso" ? "selo rev" : "selo ok" }, c.verificacao)));
    }
  }
  montar(cabecalho("Novo trabalho", "Escolha de onde vêm os produtos. O motor da Receita confere cada um e devolve o cadastro fiscal para importar no ERP."), trilha, lista,
    h("div", { class: "acoes", style: "margin-top:18px" },
      h("button", { class: "btn primario", disabled: !estado.origem, onclick: () => { estado.passo = 2; estado.erro = null; vistaNovo(); } }, "Continuar"),
      h("a", { href: "#/conexoes" }, "Gerenciar conexões")));
}
const nomeOrigem = id => estado.catalogo?.conexoes.find(c => c.id === id)?.nome || id;

function formParametros() {
  const c = estado.origem, salvo = credenciais(c.id) || {}, usaCred = c.campos.some(f => f.segredo);
  const prefs = Guarda.ler("rf.prefs", {});
  const ent = {};
  const campo = (f, padrao) => {
    const id = `f-${f.nome}`;
    ent[f.nome] = h("input", { id, name: f.nome, type: f.tipo === "arquivo" ? "file" : f.tipo === "senha" ? "password" : f.tipo === "data" ? "date" : "text",
      accept: f.aceita, required: f.tipo !== "arquivo" || true, value: f.tipo === "arquivo" ? false : (salvo[f.nome] ?? padrao ?? ""), autocomplete: "off", maxlength: f.nome === "uf" ? "2" : false });
    return h("div", { class: "campo" }, h("label", { for: id }, f.rotulo), ent[f.nome]);
  };
  const lembrar = h("input", { type: "checkbox", id: "lembrar", checked: !!localStorage.getItem(`rf.cred.${c.id}`) });
  const erro = h("div", { class: "erro", role: "alert", hidden: !estado.erro }, estado.erro || "");
  const form = h("form", { class: "painel", onsubmit: async e => {
    e.preventDefault();
    const fd = new FormData();
    const cred = {};
    for (const f of c.campos) {
      if (f.tipo === "arquivo") fd.append(f.nome, ent[f.nome].files[0]);
      else { fd.append(f.nome, ent[f.nome].value); if (!f.volatil) cred[f.nome] = ent[f.nome].value; }
    }
    fd.append("uf", ent.uf.value); fd.append("data", ent.data.value);
    Guarda.gravar("rf.prefs", { uf: ent.uf.value, data: ent.data.value }, true);
    if (usaCred) Guarda.gravar(`rf.cred.${c.id}`, cred, lembrar.checked);
    estado.passo = 3; estado.executando = true; estado.resultado = null; estado.erro = null; estado.filtro = "todos"; estado.busca = ""; estado.visiveis = 100; estado.aberta = null;
    vistaNovo();
    try {
      const r = await api(`/api/importar/${c.id}`, { method: "POST", body: fd });
      estado.resultado = await r.json();
      guardarHistorico(estado.resultado);
    } catch (x) { estado.erro = x.message; estado.passo = 2; }
    estado.executando = false;
    vistaNovo();
  } },
    h("h2", { style: "margin-bottom:16px" }, c.nome), erro,
    c.campos.filter(f => f.tipo === "arquivo").map(f => campo(f)),
    h("div", { class: c.campos.length > 3 ? "grade2" : "" }, c.campos.filter(f => f.tipo !== "arquivo").map(f => campo(f))),
    h("div", { class: "grade2" }, estado.catalogo.parametros.map(p => campo(p, prefs[p.nome] ?? p.padrao))),
    usaCred && h("label", { class: "marcar", for: "lembrar" }, lembrar, h("span", {}, "Lembrar as credenciais neste navegador. Ficam só aqui, nunca no servidor. Sem marcar, valem até fechar a aba.")),
    h("div", { class: "acoes" }, h("button", { class: "btn primario", type: "submit" }, "Executar e conferir no motor"),
      h("button", { class: "btn", type: "button", onclick: () => { estado.passo = 1; vistaNovo(); } }, "Voltar")));
  return form;
}

function execucao() {
  return h("div", { class: "exec", role: "status", "aria-live": "polite" },
    h("h2", {}, "Conferindo no motor da Receita"), h("p", { style: "color:var(--tinta-2);margin-top:6px" }, `Lendo os produtos de ${nomeOrigem(estado.origem.id)} e validando cada NCM. Listas grandes levam alguns minutos.`),
    h("div", { class: "barra" }, h("i")));
}

function resultado() {
  const r = estado.resultado, res = r.resumo;
  const cont = { todos: res.total, pronto: res.prontos, revisar: res.revisar, erro: res.com_erro, sem: res.sem_ncm };
  const aviso = r.modoCalculadora === "mock" && h("div", { class: "erro" }, "Resultado de teste: gerado por simulador, não pela calculadora da Receita.");
  const corpo = h("div", { id: "corpo-livro" }), rodape = h("div", { class: "rodape-tabela", id: "rodape-livro" });
  const filtros = h("div", { class: "filtros", role: "group", "aria-label": "Filtrar por situação" }, FILTROS.map(([id, nome]) =>
    h("button", { "aria-pressed": String(estado.filtro === id), onclick: () => { estado.filtro = id; estado.visiveis = 100; estado.aberta = null; desenhar(); filtros.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(FILTROS[i][0] === id))); } },
      h("b", {}, (cont[id] ?? 0).toLocaleString("pt-BR")), nome)));
  const busca = h("input", { class: "busca", type: "search", placeholder: "Buscar por código, produto ou NCM", "aria-label": "Buscar", value: estado.busca,
    oninput: e => { estado.busca = e.target.value; estado.visiveis = 100; estado.aberta = null; desenhar(); } });
  const menuLista = h("div", { class: "menu-lista", hidden: true, role: "menu" },
    [["xlsx", "Excel (.xlsx)", "Planilha formatada"], ["csv", "CSV (.csv)", "Abre no Excel com acentos"], ["json", "JSON", "Para integrar com outros sistemas"], ["copiar", "Copiar tabela", "Cola direto numa planilha"]].map(([t, n, d]) =>
      h("button", { role: "menuitem", onclick: async ev => { menuLista.hidden = true; const b = ev.currentTarget; try { await exportar(t); if (t === "copiar") aviso2("Tabela copiada."); } catch (x) { aviso2(x.message, true); } } }, n, h("small", {}, d))));
  const btnExp = h("button", { class: "btn primario", "aria-haspopup": "menu", onclick: () => { menuLista.hidden = !menuLista.hidden; } }, "Exportar");
  const status = h("span", { role: "status", style: "color:var(--tinta-2);font-size:.9rem" });
  function aviso2(t, e) { status.textContent = t; status.style.color = e ? "var(--err)" : "var(--ok)"; setTimeout(() => status.textContent = "", 4000); }

  function desenhar() {
    const lin = linhasFiltradas();
    if (!lin.length) { corpo.replaceChildren(h("div", { class: "vazio" }, h("h2", {}, "Nenhum produto neste filtro"), h("p", {}, "Troque o filtro ou limpe a busca."))); rodape.replaceChildren(); return; }
    const tbody = h("tbody", {});
    lin.slice(0, estado.visiveis).forEach((l, i) => {
      const [cls, txt] = ROTULO[categoria(l)], aberta = estado.aberta === i;
      tbody.append(h("tr", { class: "linha" + (aberta ? " aberta" : ""), tabindex: "0", "aria-expanded": String(aberta),
        onclick: () => { estado.aberta = aberta ? null : i; desenhar(); }, onkeydown: e => { if (e.key === "Enter") { estado.aberta = aberta ? null : i; desenhar(); } } },
        h("td", { class: "cod" }, l.codigo), h("td", { class: "desc" }, l.descricao || "—"), h("td", { class: "cod" }, l.ncm || "—"),
        h("td", { class: "cod" }, l.cst || "—"), h("td", { class: "cod" }, l.cclasstrib || "—"),
        h("td", {}, h("span", { class: `sit ${cls}` }, txt)), h("td", {}, l.o_que_fazer || "—")));
      if (aberta) tbody.append(h("tr", { class: "detalhe" }, h("td", { colspan: "7" }, h("dl", {},
        h("dt", {}, "Classificação sugerida"), h("dd", {}, l.descricao_classificacao || "—"),
        h("dt", {}, "Conferência no motor"), h("dd", {}, l.validacao_motor || "não executada"),
        l.problema && [h("dt", {}, "Problema"), h("dd", {}, l.problema)],
        h("dt", {}, "O que fazer"), h("dd", {}, l.o_que_fazer || "—")))));
    });
    corpo.replaceChildren(h("div", { class: "livro" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Código", "Produto", "NCM", "CST", "cClassTrib", "Situação", "O que fazer"].map(t => h("th", { scope: "col" }, t)))), tbody)));
    rodape.replaceChildren(...[h("span", {}, `Mostrando ${Math.min(estado.visiveis, lin.length).toLocaleString("pt-BR")} de ${lin.length.toLocaleString("pt-BR")}. A exportação leva todas as linhas do filtro atual.`),
      lin.length > estado.visiveis ? h("button", { class: "btn", onclick: () => { estado.visiveis += 200; desenhar(); } }, "Mostrar mais 200") : null].filter(Boolean));
  }
  desenhar();
  return h("div", {}, aviso, h("div", { class: "faixa" }, filtros, h("div", { class: "acoes" }, busca, status, h("div", { class: "menu" }, btnExp, menuLista))), corpo, rodape);
}

/* Conexões ---------------------------------------------------- */
async function vistaConexoes() {
  if (!estado.catalogo) await carregarCatalogo();
  const lista = h("div", { class: "lista" });
  for (const g of ["Arquivo", "API"]) {
    lista.append(h("div", { class: "grupo" }, g === "Arquivo" ? "Arquivos: não guardam credenciais" : "APIs: credenciais ficam só neste navegador"));
    for (const c of estado.catalogo.conexoes.filter(x => x.grupo === g)) {
      const cfg = configurada(c);
      lista.append(h("div", { style: "display:grid;grid-template-columns:1fr auto auto;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--linha)" },
        h("div", {}, h("div", { style: "font-weight:600" }, c.nome), h("div", { style: "color:var(--tinta-2);font-size:.9rem" }, c.descricao)),
        h("span", { class: c.verificacao === "Confirmar no 1º uso" ? "selo rev" : "selo ok", title: "Situação da verificação do conector" }, c.verificacao),
        cfg === null ? h("button", { class: "btn", onclick: () => { estado.origem = c; estado.passo = 2; location.hash = "#/novo"; } }, "Usar")
          : h("button", { class: "btn", onclick: () => gaveta(c) }, cfg ? "Editar" : "Configurar")));
    }
  }
  montar(cabecalho("Conexões", "Escolha de onde vêm os produtos. Conectores marcados com “Confirmar no 1º uso” seguem a documentação do sistema, mas ainda não foram testados com uma conta real."), lista,
    h("p", { style: "margin-top:18px;color:var(--tinta-2);max-width:70ch" }, "Precisa de outro sistema? O arquivo SPED serve para qualquer ERP, porque todo contador consegue gerá-lo."));
}

function gaveta(c) {
  const g = $("#gaveta"), salvo = credenciais(c.id) || {}, ent = {};
  const campos = c.campos.filter(f => !f.volatil);
  const lembrar = h("input", { type: "checkbox", id: "g-lembrar", checked: !!localStorage.getItem(`rf.cred.${c.id}`) });
  g.replaceChildren(h("form", { class: "gaveta-corpo", method: "dialog", onsubmit: e => {
    e.preventDefault();
    Guarda.gravar(`rf.cred.${c.id}`, Object.fromEntries(campos.map(f => [f.nome, ent[f.nome].value])), lembrar.checked);
    g.close(); vistaConexoes();
  } },
    h("h2", { id: "gaveta-titulo" }, c.nome), h("p", { style: "color:var(--tinta-2)" }, c.descricao),
    c.verificacao === "Confirmar no 1º uso" && h("div", { class: "nota" }, "Conector baseado na documentação pública. No primeiro uso com uma conta real, confira o resultado."),
    campos.map(f => h("div", { class: "campo" }, h("label", { for: `g-${f.nome}` }, f.rotulo),
      (ent[f.nome] = h("input", { id: `g-${f.nome}`, type: f.tipo === "senha" ? "password" : "text", value: salvo[f.nome] || "", autocomplete: "off", required: true })))),
    h("label", { class: "marcar", for: "g-lembrar" }, lembrar, h("span", {}, "Lembrar neste navegador. Sem marcar, valem até fechar a aba.")),
    h("div", { class: "acoes", style: "margin-top:auto" },
      h("button", { class: "btn primario", type: "submit" }, "Salvar conexão"),
      h("button", { class: "btn", type: "button", onclick: () => g.close() }, "Cancelar"),
      credenciais(c.id) && h("button", { class: "btn leve", type: "button", onclick: () => { Guarda.apagar(`rf.cred.${c.id}`); g.close(); vistaConexoes(); } }, "Remover"))));
  g.showModal();
}

/* Histórico --------------------------------------------------- */
function guardarHistorico(r) {
  const itens = Guarda.ler("rf.hist", []);
  itens.unshift({ ...r, linhas: r.linhas.slice(0, 1500), truncado: r.linhas.length > 1500 });
  try { Guarda.gravar("rf.hist", itens.slice(0, 10), true); } catch { /* quota */ }
}
function vistaHistorico() {
  const itens = Guarda.ler("rf.hist", []);
  if (!itens.length) return montar(cabecalho("Histórico"), h("div", { class: "vazio" }, h("h2", {}, "Nenhum trabalho ainda"), h("p", {}, "Os últimos 10 resultados ficam guardados neste navegador."), h("p", { style: "margin-top:14px" }, h("a", { class: "btn primario", href: "#/novo", style: "text-decoration:none" }, "Criar o primeiro trabalho"))));
  const lista = h("div", { class: "lista" }, itens.map((r, i) => h("div", { style: "display:grid;grid-template-columns:1fr auto auto;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--linha)" },
    h("div", {}, h("div", { style: "font-weight:600" }, nomeOrigem(r.conector)), h("div", { style: "color:var(--tinta-2);font-size:.9rem" },
      `${new Date(r.geradoEm).toLocaleString("pt-BR")} · ${r.resumo.total.toLocaleString("pt-BR")} produtos · ${r.resumo.prontos} prontos · ${r.resumo.revisar} revisar · ${r.resumo.com_erro} com erro${r.truncado ? " · mostrando as primeiras 1.500 linhas" : ""}`)),
    h("button", { class: "btn", onclick: () => { estado.resultado = r; estado.passo = 3; estado.executando = false; estado.filtro = "todos"; estado.busca = ""; estado.visiveis = 100; estado.aberta = null; location.hash = "#/novo"; vistaNovo(); } }, "Abrir"),
    h("button", { class: "btn leve", onclick: () => { Guarda.gravar("rf.hist", itens.filter((_, j) => j !== i), true); vistaHistorico(); } }, "Excluir"))));
  montar(cabecalho("Histórico", "Resultados guardados só neste navegador."), lista);
}

/* Ajustes ----------------------------------------------------- */
async function vistaAjustes() {
  const chave = h("input", { id: "chave", type: "password", value: Guarda.ler("rf.apikey", ""), autocomplete: "off" });
  const motor = h("dl", { class: "motor-info" }, h("dt", {}, "Motor"), h("dd", {}, "Consultando…"));
  montar(cabecalho("Ajustes"), h("div", { class: "ajustes-grade" },
    h("section", { class: "painel" }, h("h2", { style: "margin-bottom:14px" }, "Motor de cálculo"), motor),
    h("section", { class: "painel" }, h("h2", { style: "margin-bottom:6px" }, "Chave de acesso"),
      h("p", { style: "color:var(--tinta-2);margin-bottom:14px" }, "Só é necessária se o servidor foi iniciado com chaves de API (API_KEYS)."),
      h("div", { class: "campo" }, h("label", { for: "chave" }, "Chave (X-API-Key)"), chave),
      h("div", { class: "acoes" }, h("button", { class: "btn primario", onclick: () => { chave.value ? Guarda.gravar("rf.apikey", chave.value, false) : Guarda.apagar("rf.apikey"); atualizarMotor(); } }, "Salvar chave"))),
    h("section", { class: "painel" }, h("h2", { style: "margin-bottom:6px" }, "Dados neste navegador"),
      h("p", { style: "color:var(--tinta-2);margin-bottom:14px" }, "Credenciais de conexões, chave de acesso e histórico ficam guardados aqui, nunca no servidor."),
      h("button", { class: "btn", onclick: () => { if (confirm("Apagar credenciais, chave e histórico guardados neste navegador?")) { [...Object.keys(localStorage), ...Object.keys(sessionStorage)].filter(k => k.startsWith("rf.")).forEach(k => Guarda.apagar(k)); vistaAjustes(); } } }, "Apagar tudo"))));
  try {
    const d = await (await api("/saude")).json(), v = d.versao || {};
    motor.replaceChildren(h("dt", {}, "Situação"), h("dd", {}, h("span", { class: "ponto ok" }), "Conectado"), h("dt", {}, "Origem do cálculo"), h("dd", {}, d.modo === "oficial" ? "Calculadora oficial da Receita Federal" : "Simulador de teste (resultados não valem)"),
      h("dt", {}, "Versão do motor"), h("dd", {}, v.versaoApp || "—"), h("dt", {}, "Base de dados"), h("dd", {}, `${v.versaoDb || "—"} · ${v.dataVersaoDb || ""}`), h("dt", {}, "Ambiente"), h("dd", {}, v.ambiente || "—"));
  } catch (x) { motor.replaceChildren(h("dt", {}, "Situação"), h("dd", {}, h("span", { class: "ponto err" }), x.message)); }
}

/* ---------- infraestrutura ---------- */
async function carregarCatalogo() {
  try { estado.catalogo = await (await api("/api/conexoes")).json(); }
  catch (x) { estado.catalogo = { conexoes: [], parametros: [] }; montar(cabecalho("Reforma Fiscal"), h("div", { class: "erro" }, x.message), h("a", { class: "btn", href: "#/ajustes" }, "Abrir ajustes")); throw x; }
}
async function atualizarMotor() {
  const el = $("#motor-estado");
  try { const d = await (await api("/saude")).json(); el.replaceChildren(h("span", { class: "ponto ok" }), h("b", {}, d.modo === "oficial" ? "Motor da Receita" : "Modo de teste"), h("br"), (d.versao?.versaoApp ? `v${d.versao.versaoApp} · base ${d.versao.dataVersaoDb || "?"}` : "Resultados não valem")); }
  catch { el.replaceChildren(h("span", { class: "ponto err" }), h("b", {}, "Motor indisponível")); }
}
function rotear() {
  const rota = (location.hash.replace(/^#\//, "") || "novo").split("?")[0];
  document.querySelectorAll(".rail nav a").forEach(a => a.getAttribute("data-rota") === rota ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  ({ novo: vistaNovo, conexoes: vistaConexoes, historico: vistaHistorico, ajustes: vistaAjustes }[rota] || vistaNovo)();
}
window.addEventListener("hashchange", rotear);
document.addEventListener("click", e => { if (!e.target.closest(".menu")) document.querySelectorAll(".menu-lista").forEach(m => m.hidden = true); });
atualizarMotor();
rotear();
