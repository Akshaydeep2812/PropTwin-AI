import { expect, test } from "@playwright/test";

/**
 * The end-to-end workflow from the project requirements, in a real browser against the real API, MySQL, trained
 * model and local blockchain. Nothing is mocked. Each numbered step matches the requirements' list.
 */
const PASSWORD = "e2e-long-enough-password";
const SHOTS = process.env.E2E_SCREENSHOT_DIR;
const RPC_URL = process.env.E2E_RPC_URL || "http://127.0.0.1:8545";

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test("register, value, twin, simulate, commit, verify and view history", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const failedRequests = [];
  page.on("response", (response) => {
    if (response.status() >= 400) failedRequests.push(`${response.request().method()} ${response.status()} ${response.url()}`);
  });
  const email = `e2e-${Date.now()}@example.com`;
  const title = `E2E apartment ${Date.now()}`;

  await page.goto("/");
  await shot(page, "01-landing");

  // 1. Register a user.
  await page.goto("/register");
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Welcome, E2E Owner" })).toBeVisible();

  // 2. Log in, after signing out, to prove the credentials and not just the registration session.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Explore listings" })).toBeVisible();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Welcome, E2E Owner" })).toBeVisible();

  // A page reload must restore the session from the refresh cookie.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome, E2E Owner" })).toBeVisible();

  // 3. Create a property.
  await page.goto("/properties/new");
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Street address").fill("1 Private Test Road");
  await page.getByLabel("Locality").fill("Riverside");
  await page.getByLabel("City").fill("Sample City");
  await page.getByLabel("State").fill("Demo State South");
  await page.getByLabel("Postal code").fill("500001");
  await page.getByLabel("Built-up area (sq ft)").fill("1250");
  await page.getByLabel("Construction year").fill("2015");
  await page.getByLabel("Bedrooms").fill("2");
  await page.getByLabel("Bathrooms").fill("2");
  await page.getByLabel("Condition").selectOption("good");
  await page.getByLabel("Monthly rent").fill("30000");
  await page.getByLabel("Amenities").fill("gym, lift");
  await page.getByRole("button", { name: "Register property" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const propertyId = page.url().split("/properties/")[1];
  await shot(page, "02-property");

  // A full reload of a private draft must still show it to its owner.
  await page.reload();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByRole("link", { name: "Edit" })).toBeVisible();

  // 4. Request an AI valuation, and confirm that the figure is the real model's output.
  await page.goto(`/valuations?property=${propertyId}`);
  const valuationResponse = page.waitForResponse((response) => response.url().endsWith("/valuations/predict"));
  await page.getByRole("button", { name: "Predict valuation" }).first().click();
  const valuation = await (await valuationResponse).json();
  expect(valuation.model_version).toBeTruthy();
  await expect(page.getByTestId("predicted-value")).toBeVisible();
  const shownValue = (await page.getByTestId("predicted-value").innerText()).replace(/[^\d]/g, "");
  expect(shownValue).toBe(String(Math.round(Number(valuation.predicted_value))));
  await expect(page.getByText("AI estimate").first()).toBeVisible();
  await expect(page.getByText(/not a guaranteed sale price/)).toBeVisible();
  // No floor was entered, so it must be disclosed as a limitation and must not appear as a factor.
  expect(valuation.factors.map((factor) => factor.factor)).not.toContain("Floor");
  await expect(page.getByText(/floor_number/)).toBeVisible();
  await shot(page, "03-valuation");

  // 5. Create a digital twin.
  await page.goto(`/properties/${propertyId}/twin`);
  await page.getByRole("button", { name: "Create digital twin" }).click();
  await expect(page.getByRole("heading", { name: "Digital twin workspace" })).toBeVisible();
  await expect(page.getByText(/no live sensor feed/)).toBeVisible();

  // 6. Run a market simulation. The result must follow the published formula exactly.
  await page.getByRole("button", { name: "Market -10%" }).click();
  const simulationResponse = page.waitForResponse((response) => response.url().endsWith("/simulate"));
  await page.getByRole("button", { name: "Run scenario" }).click();
  const simulation = await (await simulationResponse).json();
  expect(simulation.method).toBe("formula");
  expect(Number(simulation.scenario_value)).toBeCloseTo(Number(simulation.baseline_value) * 0.9, 1);
  await expect(page.getByText("Hypothetical simulation").first()).toBeVisible();
  await expect(page.getByText(/not a new model prediction/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Market down 10%" })).toBeVisible();
  await page.waitForTimeout(300);
  await shot(page, "04-twin");

  // 7. Register the record on the local blockchain, through the UI's confirmation dialog.
  await page.goto(`/properties/${propertyId}/blockchain`);
  await page.getByRole("button", { name: "Register on blockchain" }).click();
  const registerResponse = page.waitForResponse((response) => response.url().endsWith("/register"));
  await page.getByRole("dialog").getByRole("button", { name: "Submit transaction" }).click();
  const transaction = await (await registerResponse).json();
  expect(transaction.status).toBe("submitted");
  expect(transaction.tx_hash).toMatch(/^0x[0-9a-f]{64}$/);

  // 8. Retrieve the transaction receipt. The page only shows this once the server has checked the receipt.
  await expect(page.getByText(/Confirmed in block/)).toBeVisible({ timeout: 30000 });
  const receipt = await page.evaluate(async ({ hash, rpcUrl }) => {
    const response = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_getTransactionReceipt", params: [hash] }),
    });
    return (await response.json()).result;
  }, { hash: transaction.tx_hash, rpcUrl: RPC_URL });
  expect(receipt.status).toBe("0x1");

  // 9. Verify the record hash.
  await page.getByRole("button", { name: "Check record integrity" }).click();
  await expect(page.getByTestId("integrity-result")).toHaveAttribute("data-result", "match");
  await page.waitForTimeout(200);
  await shot(page, "05-blockchain");

  // 10. View the history in the frontend.
  await page.reload();
  await expect(page.getByRole("cell", { name: "PropertyRegistered" })).toBeVisible();
  await expect(page.getByText(transaction.tx_hash.slice(0, 10))).toBeVisible();

  await page.goto(`/valuations/history?property=${propertyId}`);
  await expect(page.getByRole("heading", { name: "All estimates" })).toBeVisible();
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Latest valuations" })).toBeVisible();
  await expect(page.getByRole("link", { name: title })).toBeVisible();
  await page.waitForTimeout(300);
  await shot(page, "06-dashboard");

  // Beyond the required list: a change to a covered field is detected, and names the field.
  await page.goto(`/properties/${propertyId}/edit`);
  await page.getByLabel("Bedrooms").fill("5");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await page.goto(`/properties/${propertyId}/blockchain`);
  await page.getByRole("button", { name: "Check record integrity" }).click();
  await expect(page.getByTestId("integrity-result")).toHaveAttribute("data-result", "mismatch");
  await expect(page.getByTestId("integrity-result")).toContainText("Bedrooms");

  // A 404 on these two lookups is the API's way to say "not created yet", and the pages handle it. Anything else is a defect.
  const expectedAbsent = /^GET 404 .*\/properties\/[^/]+\/twin$|^GET 404 .*\/blockchain\/properties\/[^/]+\/record$/;
  expect(failedRequests.filter((request) => !expectedAbsent.test(request))).toEqual([]);
  expect(consoleErrors.filter((text) => !text.startsWith("Failed to load resource"))).toEqual([]);
});

test("a guest can browse, but private data and protected pages stay out of reach", async ({ page }) => {
  const requests = [];
  page.on("response", async (response) => {
    if (response.url().includes("/api/v1/properties") && response.request().method() === "GET") requests.push(await response.text().catch(() => ""));
  });
  await page.goto("/properties?q=DEMO");
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await expect(page.getByText("Synthetic demo data").first()).toBeVisible();
  await shot(page, "07-listing");
  for (const body of requests) expect(body).not.toContain("Example Road");

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("the layout works at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 800 });
  await page.goto("/properties?q=DEMO");
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  await expect(page.getByText("Synthetic demo data").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await shot(page, "08-mobile");
});
