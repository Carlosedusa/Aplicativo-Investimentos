// Teste de ponta a ponta em tela de celular. Rodar: node --test web/tests
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const net = require("node:net");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..", "..");
const TOKEN = "e2e-token";
let server, browser, port, workdir;

function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer().listen(0, () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

before(async () => {
  port = await freePort();
  workdir = fs.mkdtempSync(path.join(os.tmpdir(), "daytrader-e2e-"));
  server = spawn("python3", ["-m", "uvicorn", "app.asgi:app", "--port", String(port)], {
    cwd: path.join(ROOT, "server"),
    env: { ...process.env, API_TOKEN: TOKEN, WORKDIR: workdir, FAKE_ENGINE: "1", STARTING_CASH: "5000" },
    stdio: "ignore",
  });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/health`)).ok) break; } catch { /* ainda subindo */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  browser = await chromium.launch();
});

after(async () => {
  if (browser) await browser.close();
  if (server) server.kill();
  fs.rmSync(workdir, { recursive: true, force: true });
});

async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${port}/`);
  return page;
}
const shot = async (page, name) => { if (process.env.SHOT) await page.screenshot({ path: path.join(process.env.SHOT, name + ".png") }); };

async function login(page) {
  await page.getByLabel("Token").fill(TOKEN);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: /^Scanner/ }).waitFor();
}

test("wrong token shows a message", async () => {
  const page = await newPage();
  await page.getByLabel("Token").fill("errado");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByText("Token inválido").waitFor();
});

test("risk banner is visible on every screen", async () => {
  const page = await newPage();
  await login(page);
  for (const tab of ["Scanner", "Ativo", "Ordem", "Carteira"]) {
    await page.locator("#tabs").getByRole("button", { name: tab }).click();
    assert.ok(await page.getByText("a maioria de quem opera na bolsa perde dinheiro").isVisible(), tab);
  }
});

async function scan(page) {
  await page.getByRole("button", { name: "Varrer o Ibovespa" }).click();
  await page.getByText(/ações analisadas/).waitFor();
  await page.getByText(/Chance de chegar ao alvo/).first().waitFor();
  await page.getByText(/RECOMENDADA PARA COMPRAR|Nenhuma ação recomendada/).first().waitFor();
}

test("swing scan to paper trade flow", async () => {
  const page = await newPage();
  await login(page);
  await scan(page);
  await shot(page, "1-scanner");
  const first = page.locator("button.hit").first();
  const sym = (await first.locator("strong").innerText()).trim();
  await first.click();
  await page.getByText(/Plano \(swing/).waitFor();
  await page.getByText("Chance (simulação do último ano)").waitFor();
  await shot(page, "2-ativo");
  await page.getByRole("button", { name: "Montar ordem de teste" }).click();
  await page.getByRole("button", { name: "Calcular tamanho" }).click();
  await page.getByText("Aprovado pelo Risco").waitFor();
  await shot(page, "3-ordem");
  await page.getByRole("button", { name: "Confirmar ordem de teste" }).click();
  await page.getByText("Ordem de teste enviada.").waitFor();
  await page.getByText(new RegExp(sym)).first().waitFor();
  await page.locator("svg.chart").waitFor();
  await shot(page, "4-carteira");
  const r = await fetch(`http://127.0.0.1:${port}/paper/positions`, { headers: { Authorization: "Bearer " + TOKEN } });
  const pos = await r.json();
  assert.equal(pos.length, 1);
  assert.equal(pos[0].symbol, sym);
  assert.equal(pos[0].horizon_days, 15);
});

test("blocked order cannot be confirmed", async () => {
  const page = await newPage();
  await login(page);
  await page.route("**/swing/order/preview", (route) => route.fulfill({ json: { verdict: "BLOCK", reasons: ["Bolsa fechada agora."], warnings: [], order: null } }));
  await scan(page);
  await page.locator("button.hit").first().click();
  await page.getByText(/Plano \(swing/).waitFor();
  await page.locator("#tabs").getByRole("button", { name: "Ordem" }).click();
  await page.getByRole("button", { name: "Calcular tamanho" }).click();
  await page.getByText("Bloqueado pelo Risco").waitFor();
  assert.equal(await page.getByRole("button", { name: "Confirmar ordem de teste" }).isDisabled(), true);
});

test("chart zooms and pans", async () => {
  const page = await newPage();
  await login(page);
  await scan(page);
  await page.locator("button.hit").first().click();
  await page.locator("svg.chart").waitFor();
  const svg = page.locator("svg.chart");
  await page.waitForFunction(() => document.querySelectorAll("svg.chart rect.body").length > 0);
  const n0 = await svg.locator("rect.body").count();
  await page.getByRole("button", { name: "Aproximar" }).click();
  const n1 = await svg.locator("rect.body").count();
  assert.ok(n1 < n0, "zoom reduz o número de velas visíveis");
  const before = await svg.locator("rect.body").first().getAttribute("x");
  const box = await svg.boundingBox();
  await page.mouse.move(box.x + 100, box.y + 100);
  await page.mouse.down(); await page.mouse.move(box.x + 160, box.y + 130, { steps: 5 }); await page.mouse.up();
  const after = await svg.locator("rect.body").first().getAttribute("x");
  assert.notEqual(before, after, "arrastar move o gráfico");
});
