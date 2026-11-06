import { expect, test } from "@playwright/test";
import { JsonRpcProvider, Wallet } from "../../blockchain/node_modules/ethers/lib.esm/index.js";

/**
 * Every role's pages, in a real browser against the real stack. Wallet signing uses a throwaway random key behind the
 * standard EIP-1193 interface, so the app's wallet code and the on-chain transactions are the real ones.
 */
const PASSWORD = "e2e-long-enough-password";
const DEMO_PASSWORD = process.env.DEMO_PASSWORD;
const RPC_URL = process.env.E2E_RPC_URL || "http://127.0.0.1:8545";
const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const PDF = { name: "deed.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 e2e test document") };
const PNG = {
  name: "front.png",
  mimeType: "image/png",
  buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64"),
};

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

const unique = (prefix) => `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

async function register(page, role = "owner") {
  const email = `${unique(role)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Your name").fill(`E2E ${role}`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("I want to").selectOption(role);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: `Welcome, E2E ${role}` })).toBeVisible();
  return email;
}

async function login(page, email, password) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /^Welcome/ })).toBeVisible();
}

async function createProperty(page, { listed = false } = {}) {
  const title = unique("E2E property");
  await page.goto("/properties/new");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Listing status").selectOption(listed ? "listed" : "draft");
  await page.getByLabel("Street address").fill("9 Secret Test Lane");
  await page.getByLabel("Locality").fill("Riverside");
  await page.getByLabel("City").fill("Sample City");
  await page.getByLabel("State").fill("Demo State South");
  await page.getByLabel("Postal code").fill("500001");
  await page.getByLabel("Built-up area (sq ft)").fill("1100");
  await page.getByLabel("Bedrooms").fill("2");
  await page.getByLabel("Floor number").fill("3");
  await page.getByLabel("Total floors").fill("10");
  await page.getByLabel("Asking price").fill("9000000");
  await page.getByLabel("Monthly rent").fill("30000");
  await page.getByRole("button", { name: "Register property" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  return { title, id: page.url().split("/properties/")[1] };
}

/** Installs a browser wallet whose key lives in this test process, funded on the local chain. */
async function installWallet(page) {
  const provider = new JsonRpcProvider(RPC_URL);
  const wallet = Wallet.createRandom().connect(provider);
  await provider.send("hardhat_setBalance", [wallet.address, "0x56BC75E2D63100000"]);
  await page.exposeFunction("__walletRequest", async ({ method, params }) => {
    if (method === "eth_requestAccounts") return [wallet.address];
    if (method === "eth_chainId") return `0x${(await provider.getNetwork()).chainId.toString(16)}`;
    if (method === "personal_sign") return wallet.signMessage(params[0]);
    if (method === "eth_sendTransaction") return (await wallet.sendTransaction({ to: params[0].to, data: params[0].data })).hash;
    throw new Error(`Unsupported wallet method ${method}`);
  });
  await page.addInitScript(() => {
    window.ethereum = { request: (args) => window.__walletRequest(args) };
  });
  return wallet;
}

async function linkWallet(page, wallet) {
  await page.goto("/profile");
  await page.getByRole("button", { name: "Connect and link wallet" }).click();
  await expect(page.getByText(wallet.address)).toBeVisible();
}

test("owner, verifier: documents, review, decision and notification", async ({ browser }) => {
  test.skip(!DEMO_PASSWORD, "Set DEMO_PASSWORD to use the seeded verifier account.");
  const ownerPage = await (await browser.newContext()).newPage();
  await register(ownerPage);
  const { title, id } = await createProperty(ownerPage);

  await ownerPage.locator('input[accept^="image/"]').first().setInputFiles(PNG);
  await expect(ownerPage.getByRole("img", { name: title })).toBeVisible();

  await ownerPage.locator('input[accept^="application/pdf"]').setInputFiles(PDF);
  await expect(ownerPage.getByRole("cell", { name: "deed.pdf" })).toBeVisible();
  await ownerPage.getByRole("button", { name: "Request verification" }).click();
  await expect(ownerPage.getByText("pending").first()).toBeVisible();

  const verifierPage = await (await browser.newContext()).newPage();
  await login(verifierPage, "demo.verifier@proptwin.example", DEMO_PASSWORD);
  await verifierPage.goto("/verifier");
  await expect(verifierPage.getByRole("heading", { name: "Verification queue" })).toBeVisible();
  await verifierPage.goto(`/properties/${id}`);
  await expect(verifierPage.getByRole("cell", { name: "deed.pdf" })).toBeVisible();
  await expect(verifierPage.getByText("9 Secret Test Lane")).toBeVisible();

  await verifierPage.goto("/verifier");
  const row = verifierPage.locator("tr").filter({ hasText: "Review property" }).last();
  await row.getByRole("button", { name: "Approve" }).click();
  await verifierPage.getByRole("dialog").getByLabel("Decision notes").fill("Documents reviewed in E2E.");
  await verifierPage.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(verifierPage.getByRole("dialog")).toBeHidden();
  await shot(verifierPage, "10-verifier");

  await ownerPage.goto(`/properties/${id}`);
  await expect(ownerPage.getByText("Documents reviewed in E2E.")).toBeVisible();
  await expect(ownerPage.getByText("verified").first()).toBeVisible();
  await shot(ownerPage, "11-verified-property");
  await ownerPage.goto("/profile");
  await expect(ownerPage.getByRole("link", { name: /Verification approved/ })).toBeVisible();
});

test("investor: browse without the address, compare, save, yield and scenario", async ({ browser }) => {
  const ownerPage = await (await browser.newContext()).newPage();
  await register(ownerPage);
  const first = await createProperty(ownerPage, { listed: true });
  const second = await createProperty(ownerPage, { listed: true });
  await ownerPage.goto(`/properties/${first.id}/twin`);
  await ownerPage.getByRole("button", { name: "Create digital twin" }).click();
  await expect(ownerPage.getByRole("heading", { name: "Digital twin workspace" })).toBeVisible();

  const page = await (await browser.newContext()).newPage();
  await register(page, "investor");
  await expect(page.getByRole("link", { name: "My properties" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);

  await page.goto(`/properties/${first.id}`);
  await expect(page.getByRole("heading", { name: first.title })).toBeVisible();
  await expect(page.getByText("9 Secret Test Lane")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Edit" })).toHaveCount(0);

  await page.goto(`/properties?q=${encodeURIComponent(first.title)}`);
  await page.getByRole("button", { name: "Save to favorites" }).click();
  await expect(page.getByRole("button", { name: "Remove from favorites" })).toBeVisible();

  await page.goto("/properties?sort=newest");
  for (const { title } of [first, second]) {
    await page.locator("article").filter({ hasText: title }).getByLabel("Compare").check();
  }
  await page.getByRole("button", { name: "Compare 2 properties" }).click();
  await expect(page.getByRole("heading", { name: "Compare properties" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: second.title })).toBeVisible();
  await shot(page, "12-compare");

  await page.goto("/investor");
  await expect(page.getByRole("cell", { name: "4.00%" })).toBeVisible();
  await shot(page, "13-investor");

  await page.goto(`/simulator?property=${first.id}`);
  await page.getByRole("button", { name: "Market +5%" }).click();
  await page.getByRole("button", { name: "Run scenario" }).click();
  await expect(page.getByText("Market up 5%").first()).toBeVisible();
  await expect(page.getByText(/not a new model prediction/)).toBeVisible();
  await shot(page, "14-simulator");

  await page.goto("/admin");
  await expect(page.getByText("You do not have access to this page")).toBeVisible();
});

test("administrator: every section loads with real data", async ({ page }) => {
  test.skip(!DEMO_PASSWORD, "Set DEMO_PASSWORD to use the seeded administrator account.");
  await login(page, "demo.admin@proptwin.example", DEMO_PASSWORD);
  await page.goto("/admin");
  await page.getByLabel("Find a user").fill("demo.owner");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("cell", { name: /demo\.owner@proptwin\.example/ })).toBeVisible();
  await shot(page, "15-admin-users");

  await page.getByRole("tab", { name: "Models" }).click();
  await expect(page.getByText("active").first()).toBeVisible();
  await page.locator("td button.font-mono").first().click();
  await expect(page.getByRole("cell", { name: "Pytorch mlp" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ridge baseline" })).toBeVisible();
  await shot(page, "16-admin-models");

  await page.getByRole("tab", { name: "Reports" }).click();
  await expect(page.getByRole("heading", { name: "Reported listings" })).toBeVisible();
  await page.getByRole("tab", { name: "Transactions" }).click();
  await expect(page.getByRole("heading", { name: "Blockchain transactions" })).toBeVisible();
  await page.getByRole("tab", { name: "Audit log" }).click();
  await expect(page.getByRole("cell", { name: "user.login" }).first()).toBeVisible();
  await page.getByRole("tab", { name: "Monitoring" }).click();
  await expect(page.getByRole("heading", { name: "Prediction drift" })).toBeVisible();
  await expect(page.getByText("Reachable", { exact: true })).toBeVisible();
  await shot(page, "17-admin-monitoring");
});

test("a transfer request can be cancelled, and a valuation can be committed on-chain", async ({ browser }) => {
  const ownerPage = await (await browser.newContext()).newPage();
  const ownerWallet = await installWallet(ownerPage);
  await register(ownerPage);
  await linkWallet(ownerPage, ownerWallet);
  const { id, title } = await createProperty(ownerPage, { listed: true });

  await ownerPage.goto(`/valuations?property=${id}`);
  await ownerPage.getByRole("button", { name: "Predict valuation" }).first().click();
  await expect(ownerPage.getByTestId("predicted-value")).toBeVisible();

  await ownerPage.goto(`/properties/${id}/blockchain`);
  await ownerPage.getByRole("button", { name: "Register on blockchain" }).click();
  await ownerPage.getByRole("dialog").getByRole("button", { name: "Submit transaction" }).click();
  await expect(ownerPage.getByText(/Confirmed in block/)).toBeVisible({ timeout: 30000 });
  await ownerPage.getByRole("button", { name: "Commit latest estimate" }).click();
  await expect(ownerPage.getByRole("cell", { name: "ValuationCommitted" })).toBeVisible({ timeout: 30000 });

  const buyerPage = await (await browser.newContext()).newPage();
  const buyerWallet = await installWallet(buyerPage);
  const buyerEmail = await register(buyerPage, "investor");
  await linkWallet(buyerPage, buyerWallet);

  await ownerPage.goto("/transfers");
  await ownerPage.getByLabel("Property").selectOption({ label: title });
  await ownerPage.getByLabel("Recipient's account email").fill(buyerEmail);
  await ownerPage.getByRole("button", { name: "Create transfer" }).click();
  await ownerPage.getByRole("dialog").getByRole("button", { name: "Continue" }).click();
  await ownerPage.getByRole("button", { name: "Cancel request" }).click();
  await expect(ownerPage.getByText("Cancelled.")).toBeVisible();
});

test("two-step ownership transfer signed in real browser wallet flows", async ({ browser }) => {
  const ownerPage = await (await browser.newContext()).newPage();
  const ownerWallet = await installWallet(ownerPage);
  await register(ownerPage);
  await linkWallet(ownerPage, ownerWallet);
  const { id, title } = await createProperty(ownerPage, { listed: true });

  await ownerPage.goto(`/properties/${id}/blockchain`);
  await ownerPage.getByRole("button", { name: "Register on blockchain" }).click();
  await ownerPage.getByRole("dialog").getByRole("button", { name: "Submit transaction" }).click();
  await expect(ownerPage.getByText(/Confirmed in block/)).toBeVisible({ timeout: 30000 });
  await ownerPage.reload();
  await expect(ownerPage.getByText(ownerWallet.address)).toBeVisible();

  const buyerPage = await (await browser.newContext()).newPage();
  const buyerWallet = await installWallet(buyerPage);
  const buyerEmail = await register(buyerPage, "investor");
  await linkWallet(buyerPage, buyerWallet);

  await ownerPage.goto("/transfers");
  await expect(ownerPage.getByText(/does not transfer legal title/).first()).toBeVisible();
  await ownerPage.getByLabel("Property").selectOption({ label: title });
  await ownerPage.getByLabel("Recipient's account email").fill(buyerEmail);
  await ownerPage.getByRole("button", { name: "Create transfer" }).click();
  await ownerPage.getByRole("dialog").getByRole("button", { name: "Continue" }).click();
  await ownerPage.getByRole("button", { name: "Propose from my wallet" }).click();
  await expect(ownerPage.getByText(/Proposed on-chain/)).toBeVisible({ timeout: 30000 });

  // A proposal moves nothing: the owner can still edit, and the buyer cannot.
  await buyerPage.goto(`/properties/${id}`);
  await expect(buyerPage.getByRole("link", { name: "Edit" })).toHaveCount(0);

  await buyerPage.goto("/transfers");
  await buyerPage.getByRole("button", { name: "Accept from my wallet" }).click();
  await expect(buyerPage.getByText(/Accepted and confirmed on-chain/)).toBeVisible({ timeout: 30000 });
  await shot(buyerPage, "18-transfer");

  await buyerPage.goto(`/properties/${id}`);
  await expect(buyerPage.getByRole("link", { name: "Edit" })).toBeVisible();

  // The new owner can record a renovation, and it reaches the page.
  await buyerPage.getByLabel("Work done").fill("New kitchen");
  await buyerPage.getByLabel("Completed on").fill("2025-03-01");
  await buyerPage.getByLabel("Cost").fill("250000");
  await buyerPage.getByRole("button", { name: "Add renovation" }).click();
  await expect(buyerPage.getByRole("cell", { name: "New kitchen" })).toBeVisible();
  await expect(buyerPage.getByText("9 Secret Test Lane")).toBeVisible();

  await ownerPage.goto(`/properties/${id}`);
  await expect(ownerPage.getByRole("link", { name: "Edit" })).toHaveCount(0);

  await buyerPage.goto(`/properties/${id}/blockchain`);
  await buyerPage.getByRole("button", { name: "Check record integrity" }).click();
  await expect(buyerPage.getByTestId("integrity-result")).toHaveAttribute("data-result", "match");
  await expect(buyerPage.getByText(buyerWallet.address).first()).toBeVisible();
});
