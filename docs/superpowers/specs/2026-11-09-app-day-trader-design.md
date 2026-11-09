# App Day Trader (uso pessoal) - Especificação de design

Data: 2026-11-09

## Objetivo
App de celular, de uso pessoal, para análise de mercado de ações dos EUA usando a skill
[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT) como motor.
Destino final: app nativo Swift (SwiftUI) para iPhone. Sem Xcode no momento, então a
primeira entrega é testável aqui: servidor Python + protótipo web mobile. O app Swift
futuro consome a mesma API.

## Decisões já tomadas
- Arquitetura: servidor Python (API) + clientes finos (web agora, Swift depois).
- Módulos da v1: Scanner, Notícias, Entrada, Saída, Time Machine, Orçamento, Risco
  e ordens em modo teste (paper trading).
- Fora da v1: Alertas, Balanços (analyst), Congresso (pelosi), corretora real.
- Hospedagem do servidor: decidir depois (entrega via Docker, roda localmente agora).
- Sem dinheiro real. Nenhuma ordem sai sem confirmação explícita do usuário.

## Arquitetura
```
Cliente web (agora) / app Swift (depois)
        |  HTTPS + token fixo
        v
API FastAPI (server/)  --tarefas em segundo plano-->  engine/ (skill, intocada)
        |                                              scan.py news.py entry.py
        v                                              exit.py timemachine.py
 Livro paper (SQLite)                                  budget.py risk.py
                                                       |
                                                       v  Yahoo / SEC (gratuitos)
```
- `engine/`: cópia da skill sem alterações; a API chama cada ferramenta com `--json`.
- Operações longas (scanner, time machine) viram tarefas: o cliente recebe um `task_id`
  e consulta até concluir.
- Pasta de trabalho `trader/` mantida como a skill espera (watchlist, entry, plan...).

## Fluxo e telas
Scanner -> Notícias -> Entrada -> Saída -> Time Machine -> Orçamento -> Risco -> Ordem teste.
1. Scanner: varredura pré-mercado ou rompimento da abertura; lista de ativos.
2. Detalhe do ativo: notícias, estado da entrada (esperando/disparou), plano de saída
   (stop, alvo, saída forçada 15:55).
3. Time Machine: probabilidades (alvo, stop, aberto) e veredito em texto.
4. Ticket de teste: tamanho da posição (Orçamento), PASS/BLOCK (Risco), botão de
   confirmação explícita.
5. Posições e histórico: posições abertas, P&L, ordens fechadas.

## Ordens em modo teste (paper)
- Livro local em SQLite: caixa virtual (valor inicial configurável), ordens, posições.
- Ordem bracket: compra + stop-loss + take-profit, como a skill descreve.
- Execução simulada a preço de mercado real (Yahoo); fechamento automático no stop, no
  alvo ou às 15:55 ET, o que ocorrer primeiro.
- Entrada só após confirmação do usuário para aquela ordem exata; Risco com BLOCK
  impede a ordem.
- Ponto de extensão: interface `Broker` com implementação `PaperBroker`; uma corretora
  de teste (ex.: Alpaca paper) pode ser adicionada depois sem mudar a API.

## Segurança e limites
- Aviso permanente: setup no gráfico não é previsão; a maioria de quem faz day trade perde.
- Token fixo na API (uso pessoal), sem contas de usuário. Segredos fora do repositório.
- Dados cobrem apenas o mercado dos EUA. A SEC exige identificação (`SEC_USER_AGENT`).

## API (resumo; contrato completo em OpenAPI)
- `POST /scan/{daily|orb}` -> task; `GET /watchlist`
- `GET /news?tickers=` ; `GET /entry/{symbol}` ; `POST /exit/plan`
- `POST /timemachine/run` -> task ; `GET /tasks/{id}`
- `POST /budget/size` ; `POST /risk/check`
- `POST /paper/orders` (exige `confirm: true`) ; `GET /paper/positions` ; `GET /paper/history`

## Testes
- Servidor: testes automáticos com as fixtures da skill (sem internet).
- Livro paper: testes de P&L, stop, alvo e fechamento às 15:55.
- Web: Playwright em viewport de celular.
- OpenAPI é a especificação que o app Swift seguirá.

## Estrutura do repositório
```
engine/   skill (intocada)      server/  API + livro paper
web/      protótipo mobile      docs/    specs e contrato
ios/      (futuro) app Swift
```

## Riscos
- Yahoo é fonte não oficial: pode limitar ou mudar; tratar erro e cache.
- Tarefas longas: expor progresso e timeout.
- Simulação não garante resultado real; preços sem slippage.
