# Day Trader (modo teste)

App de uso pessoal para analisar o mercado dos EUA com a skill
[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (MIT, copiada em `engine/`).
**Só dinheiro de teste**: não há corretora nem ordens reais. Um setup no gráfico não é previsão;
a maioria de quem faz day trade perde dinheiro.

## O que tem
- `server/`: API (FastAPI) que roda a skill e mantém o livro de ordens de teste (SQLite).
- `web/`: protótipo para celular (abre no navegador).
- `engine/`: a skill, sem alterações.
- `docs/api/openapi.json`: contrato da API. O futuro app Swift (`ios/`) deve segui-lo.

## Rodar
```bash
pip install fastapi uvicorn httpx pytest
cd server
API_TOKEN=escolha-um-token WORKDIR=./data uvicorn app.asgi:app --port 8000
```
Abra `http://localhost:8000` e digite o token. Variáveis: `API_TOKEN` (obrigatória), `WORKDIR`,
`STARTING_CASH` (padrão 5000), `SEC_USER_AGENT` ("Seu Nome email@exemplo.com", exigido pela SEC).

Modo demonstração, sem internet: `FAKE_ENGINE=1` usa amostras e preço fixo.

Com Docker: `docker build -t daytrader .` e
`docker run -p 8000:8000 -e API_TOKEN=... -v daytrader-data:/data daytrader`.

## Testes
```bash
cd server && pytest                       # servidor e livro de ordens
cd engine && pytest tests                 # testes da skill
NODE_PATH=<pasta do playwright> node --test web/tests/e2e.test.js   # tela de celular
python -m app.export_openapi              # atualiza o contrato após mudar a API
```

## Limites conhecidos (v1)
- Dados do Yahoo são gratuitos e não oficiais: podem atrasar ou falhar.
- As regras de Risco por dia (número de operações, perda diária) não são alimentadas pelo livro de teste.
- Sem slippage na simulação. Veredito da skill vem em inglês.
- Sem app Swift ainda: precisa de Xcode.
