# App Day Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servidor Python (API) que expõe a skill day-trader mais um livro de ordens em modo teste (paper), e um protótipo web mobile que consome a API.

**Architecture:** `engine/` guarda a skill intocada; ela fala por arquivos JSON em uma pasta `trader/` e por linha de comando (`--json`). `server/` (FastAPI) chama cada ferramenta por subprocesso numa pasta de trabalho, devolve o JSON e roda as operações longas como tarefas em segundo plano. O `PaperBroker` (SQLite) simula ordens bracket com preços reais. `web/` é HTML/JS estático em largura de celular.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pytest, httpx, SQLite (stdlib), HTML/JS sem build, Playwright (teste do web), Docker.

**Spec:** `docs/superpowers/specs/2026-11-09-app-day-trader-design.md`

## Global Constraints

- Skill copiada para `engine/` sem alterações (MIT; manter `LICENSE`).
- Sem dinheiro real, sem corretora, sem chaves de API. Nenhuma ordem sem `confirm: true`.
- Ordem de teste é bracket: compra + stop-loss + take-profit; fecha no stop, no alvo ou às 15:55 ET.
- Token fixo (`API_TOKEN` por variável de ambiente) em toda rota exceto `/health`; sem contas.
- Só mercado dos EUA; SEC exige `SEC_USER_AGENT`.
- Aviso permanente nas telas: setup no gráfico não é previsão; a maioria de quem faz day trade perde.
- Testes não podem usar a internet (runner falso + fixtures).
- Textos da interface em português.

## Review Focus

- Yahoo fora do ar ou ferramenta com exit code != 0: a API devolve erro legível (502), nunca trava a tarefa.
- Dois cliques seguidos em "confirmar": a ordem não duplica (idempotência por `client_order_id`).
- Ordem com Risco = BLOCK: o livro paper recusa mesmo que o cliente envie `confirm: true`.
- Preço pula acima do alvo e abaixo do stop entre duas leituras: fecha no stop (pior caso).
- Caixa virtual insuficiente ou 0 ações calculadas: recusa com motivo.
- Sem token ou token errado: 401 em todas as rotas protegidas.

---

## File Structure

```
engine/                 skill copiada (trader-*/ , tests/, LICENSE)
server/pyproject.toml   dependências e pytest
server/app/main.py      cria o FastAPI, roteadores, auth
server/app/config.py    Settings (token, pasta de trabalho, caixa inicial)
server/app/engine.py    run_tool(): chama as ferramentas da skill
server/app/tasks.py     TaskManager: tarefas em segundo plano
server/app/routes_analysis.py   scan, watchlist, news, entry, exit, timemachine
server/app/routes_trade.py      budget, risk
server/app/paper/broker.py      PaperBroker + modelos
server/app/paper/prices.py      PriceFeed (Yahoo) e interface
server/app/paper/monitor.py     fecha posições no stop/alvo/15:55
server/app/routes_paper.py      ordens, posições, histórico
server/tests/           pytest (runner falso, amostras JSON)
web/                    index.html, app.js, style.css
web/tests/              Playwright
Dockerfile, README.md
```

---

### Task 1: Esqueleto, engine e runner da skill

**Files:**
- Create: `engine/` (cópia de `trader-*`, `tests/`, `LICENSE` de github.com/Jakeschincariol/day-trader-skill), `server/pyproject.toml`, `server/app/{__init__,main,config,engine}.py`, `server/tests/{conftest,test_engine,test_auth}.py`

**Interfaces:**
- Produces: `Settings(api_token: str, workdir: Path, starting_cash: float = 5000.0)` lida do ambiente (`API_TOKEN`, `WORKDIR`, `STARTING_CASH`); `run_tool(tool: str, args: list[str], workdir: Path, timeout: int = 300) -> dict` (executa `python3 engine/trader-<tool>/<script>.py <args> --json` com `cwd=workdir`, devolve o JSON; levanta `EngineError(message, returncode, stderr)`); dependência FastAPI `require_token`.

- [ ] **Step 1:** Copiar a skill para `engine/` e confirmar que os testes dela passam: `cd engine && python3 -m pytest tests -q` → todos passam.
- [ ] **Step 2: Testes** em `test_engine.py`: `test_run_tool_returns_parsed_json` (script falso que imprime `{"ok": true}` → `{"ok": True}`), `test_run_tool_raises_engine_error_on_nonzero_exit` (exit 2 → `EngineError`, `stderr` preenchido), `test_run_tool_uses_workdir_as_cwd`. Em `test_auth.py`: `test_health_is_public` (200), `test_protected_route_without_token_is_401`, `test_protected_route_with_wrong_token_is_401`.
- [ ] **Step 3:** Rodar e ver falhar: `cd server && pytest -q` → FAIL (módulos inexistentes).
- [ ] **Step 4:** Implementar `config.py`, `engine.py` (mapa `tool → (pasta, script)`: scanner/scan.py, news/news.py, entry/entry.py, exit/exit.py, timemachine/timemachine.py, budget/size.py, risk/check.py), `main.py` com `GET /health` e `require_token` (cabeçalho `Authorization: Bearer <token>`, comparação com `secrets.compare_digest`).
- [ ] **Step 5:** `pytest -q` → PASS.
- [ ] **Step 6: Commit** `feat: esqueleto do servidor e runner da skill`.

### Task 2: Tarefas em segundo plano

**Files:** Create `server/app/tasks.py`, `server/tests/test_tasks.py`; Modify `server/app/main.py` (rota `GET /tasks/{id}`)

**Interfaces:**
- Consumes: `EngineError` (Task 1).
- Produces: `TaskManager.submit(fn: Callable[[], dict]) -> str` (devolve `task_id`, executa em thread); `TaskManager.get(task_id) -> {"id", "status": "pending|running|done|error", "result": dict|None, "error": str|None}`; instância única em `app.state.tasks`.

- [ ] **Step 1: Testes:** `test_task_runs_and_returns_result` (fn devolve `{"x":1}` → status `done`, `result == {"x":1}`), `test_task_failure_is_captured_as_error` (fn levanta `EngineError("yahoo fora")` → status `error`, mensagem preservada), `test_unknown_task_is_404`.
- [ ] **Step 2:** Rodar, ver falhar. **Step 3:** Implementar com `ThreadPoolExecutor(max_workers=2)` e dicionário protegido por lock. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat: tarefas em segundo plano`.

### Task 3: Rotas de análise (scanner, notícias, entrada, saída, time machine)

**Files:** Create `server/app/routes_analysis.py`, `server/tests/samples/*.json`, `server/tests/test_routes_analysis.py`; Modify `server/app/main.py`, `server/tests/conftest.py` (fixture `fake_engine` que troca `run_tool` por um dicionário `{tool: amostra}`)

**Interfaces:**
- Consumes: `run_tool`, `TaskManager`, `require_token`.
- Produces: `POST /scan/{mode}` (`mode` ∈ `daily|orb`; corpo opcional `{symbols?: list[str], at?: "HH:MM", limit?: int}`) → `{"task_id"}`; `GET /watchlist` → conteúdo de `trader/watchlist.json` (404 se não existir); `GET /news?tickers=TSLA,NVDA&hours=12` → JSON de notícias; `GET /entry/{symbol}` → estado da entrada (`check SYMBOL --write`); `POST /exit/plan` (corpo `{stop?: str, target?: str}`) → plano e grava `trader/plan.json`; `POST /timemachine/run` (corpo `{until?: "HH:MM", seed?: int}`) → `{"task_id"}`.

- [ ] **Step 1:** Gerar amostras reais para os testes: rodar cada ferramenta com `--json` usando as fixtures da skill/`--offline` quando houver e salvar em `server/tests/samples/` (scan_orb, news, entry, exit_plan, timemachine). Se uma ferramenta não rodar offline, escrever a amostra a partir do formato descrito no `SKILL.md` dela.
- [ ] **Step 2: Testes** (com `fake_engine`): `test_scan_orb_returns_task_and_result_is_watchlist`, `test_scan_rejects_unknown_mode_422`, `test_watchlist_404_before_scan`, `test_news_passes_tickers_and_hours_to_tool`, `test_entry_returns_status_field`, `test_exit_plan_writes_plan_file`, `test_timemachine_task_result_has_probabilities`, `test_engine_failure_becomes_502_with_message` (Review Focus: Yahoo fora do ar).
- [ ] **Step 3:** Rodar, ver falhar. **Step 4:** Implementar roteadores; `EngineError` em rota síncrona → 502 `{"detail": mensagem}`. **Step 5:** PASS.
- [ ] **Step 6: Commit** `feat: rotas de análise`.

### Task 4: Orçamento e Risco

**Files:** Create `server/app/routes_trade.py`, `server/tests/test_routes_trade.py`, amostras `budget.json`/`risk.json`; Modify `server/app/main.py`

**Interfaces:**
- Produces: `POST /budget/size` (corpo `{budget: float, max_loss: float}`; grava `trader/config.json`, roda `size.py --write`) → ordem bracket `{symbol, qty, entry, stop, target, ...}`; `POST /risk/check` → `{"verdict": "PASS"|"BLOCK", "reasons": list[str]}` (a API normaliza o JSON de `check.py`).

- [ ] **Step 1: Testes:** `test_budget_returns_qty_and_bracket` (conta da skill: 50 / 5,86 → 8 ações), `test_budget_requires_plan_409` (sem `plan.json`), `test_risk_block_has_reasons`, `test_risk_pass`.
- [ ] **Step 2–5:** falhar, implementar, passar. **Step 6: Commit** `feat: orçamento e risco`.

### Task 5: PaperBroker (livro de ordens de teste)

**Files:** Create `server/app/paper/{__init__,broker,prices}.py`, `server/tests/test_paper_broker.py`

**Interfaces:**
- Produces: `PriceFeed` (protocolo: `last(symbol: str) -> float`); `YahooPriceFeed`; `PaperBroker(db_path, feed: PriceFeed, clock: Callable[[], datetime], starting_cash: float)` com:
  `place_bracket(client_order_id: str, symbol: str, qty: int, stop: float, target: float) -> Position` (compra a `feed.last`, reserva caixa; mesma `client_order_id` devolve a mesma posição sem duplicar; `qty <= 0` ou caixa insuficiente → `PaperError(motivo)`);
  `positions() -> list[Position]`; `history() -> list[ClosedTrade]`; `cash() -> float`; `tick() -> list[ClosedTrade]` (fecha o que atingiu stop, alvo ou 15:55 ET; fecha no stop se ambos foram cruzados);
  `Position(id, symbol, qty, entry, stop, target, opened_at)`; `ClosedTrade(..., exit_price, reason: "stop"|"target"|"eod", pnl: float)`.

- [ ] **Step 1: Testes** (feed e relógio falsos): `test_place_bracket_debits_cash`, `test_same_client_order_id_does_not_duplicate`, `test_zero_qty_rejected`, `test_insufficient_cash_rejected`, `test_tick_closes_at_target_with_positive_pnl`, `test_tick_closes_at_stop_with_negative_pnl` (8 ações, entrada 364,18, stop 358,32 → pnl −46,88), `test_gap_through_both_levels_closes_at_stop`, `test_tick_closes_everything_at_1555_ny` (reason `eod`), `test_state_survives_restart` (reabrir o SQLite).
- [ ] **Step 2:** Rodar, ver falhar. **Step 3:** Implementar com SQLite (tabelas `orders`, `positions`, `trades`, `account`); `YahooPriceFeed` usa o endpoint de gráfico que a skill já usa (ver `engine/trader-entry/entry.py`). **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat: livro de ordens paper`.

### Task 6: Rotas paper e monitor

**Files:** Create `server/app/paper/monitor.py`, `server/app/routes_paper.py`, `server/tests/test_routes_paper.py`; Modify `server/app/main.py` (cria o broker e inicia o monitor no startup)

**Interfaces:**
- Consumes: `PaperBroker`, `POST /risk/check` (Task 4).
- Produces: `POST /paper/orders` (corpo `{client_order_id, symbol, qty, stop, target, confirm}`) → `Position`; `confirm` ausente/`false` → 422; veredito de Risco `BLOCK` → 409 com `reasons`; `GET /paper/positions`; `GET /paper/history`; `GET /paper/account` → `{cash, equity, open_pnl, closed_pnl}`; monitor chama `broker.tick()` a cada 30 s em segundo plano.

- [ ] **Step 1: Testes:** `test_order_without_confirm_is_422`, `test_order_blocked_by_risk_is_409_even_with_confirm` (Review Focus), `test_double_post_same_client_order_id_returns_one_position`, `test_positions_and_history_endpoints`, `test_account_equity_uses_last_price`, `test_monitor_tick_closes_position`.
- [ ] **Step 2–5:** falhar, implementar, passar. **Step 6: Commit** `feat: rotas paper e monitor`.

### Task 7: Protótipo web mobile

**Files:** Create `web/{index.html,app.js,style.css}`, `server/app/main.py` (servir `web/` em `/`)

**Interfaces:**
- Consumes: todas as rotas acima; token digitado na primeira abertura e guardado em `localStorage`.
- Produces: 5 telas em largura de celular (≤ 430 px), navegação inferior: **Scanner** (botões "Pré-mercado" e "Rompimento da abertura", lista; consulta `/tasks/{id}` a cada 2 s), **Ativo** (notícias, estado da entrada, plano de saída, botão "Simular"), **Time Machine** (barras alvo/stop/aberto + veredito), **Ticket** (quantidade, Risco PASS/BLOCK, botão "Confirmar ordem de teste" desabilitado em BLOCK e durante o envio), **Carteira** (caixa, posições, histórico). Faixa fixa com o aviso de risco em todas as telas. Seguir a skill `frontend-design` para o visual.

- [ ] **Step 1:** Escrever as telas e a camada `api(path, opts)` com o cabeçalho de token e tratamento de 401/409/502 com mensagem clara em português.
- [ ] **Step 2:** Verificação manual: subir `uvicorn app.main:app` com `fake_engine` ativável por `FAKE_ENGINE=1` (usa as amostras) e abrir `http://localhost:8000`.
- [ ] **Step 3: Commit** `feat: protótipo web mobile`.

### Task 8: Teste de ponta a ponta (Playwright)

**Files:** Create `web/tests/e2e.spec.js`, `web/tests/playwright.config.js`

- [ ] **Step 1: Teste** em viewport 390×844 com `FAKE_ENGINE=1` e `FAKE_PRICES=1`: `scan_to_paper_trade_flow` (digita token → Scanner → varre → abre TSLA → Time Machine → Ticket → Risco PASS → confirma → posição aparece em Carteira com 8 ações); `blocked_order_cannot_be_confirmed` (botão desabilitado); `wrong_token_shows_message`; `risk_banner_visible_on_every_screen`.
- [ ] **Step 2:** Rodar `npx playwright test --trace off` → PASS. **Step 3: Commit** `test: e2e do protótipo`.

### Task 9: Docker, contrato OpenAPI e documentação

**Files:** Create `Dockerfile`, `README.md`, `docs/api/openapi.json` (exportado de `app.openapi()`), `server/tests/test_openapi.py`

- [ ] **Step 1: Teste** `test_openapi_snapshot_is_current` (o arquivo exportado é igual ao gerado; falha se a API mudar sem atualizar o contrato que o app Swift seguirá).
- [ ] **Step 2:** Dockerfile (python:3.12-slim, instala server, copia engine e web, `CMD uvicorn`); README em português: como rodar, variáveis (`API_TOKEN`, `SEC_USER_AGENT`, `STARTING_CASH`), aviso de risco, roteiro do app Swift (`ios/`).
- [ ] **Step 3:** Rodar toda a suíte: `pytest -q` em `server/` → PASS. **Step 4: Commit** `docs: contrato OpenAPI, Docker e README`.

---

## Self-Review

- Cobertura da spec: scanner/notícias/entrada/saída/time machine (T3), orçamento/risco (T4), paper com stop/alvo/15:55 e confirmação (T5–6), telas (T7), testes (T1–T9), Docker/OpenAPI (T9), segurança/token (T1). Fora da v1 (alertas, analyst, pelosi, corretora real, app Swift) não aparecem, como na spec.
- Tipos consistentes: `run_tool`, `TaskManager`, `PaperBroker`, `Position`, `ClosedTrade` usados com os mesmos nomes entre tarefas.
- Risco conhecido: o formato exato do JSON das ferramentas só é visto ao rodá-las (T3 Step 1); a API normaliza o que o cliente precisa.
