import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { niceTicks, paddedDomain } from "../components/charts";
import { ValuationResult } from "../components/property";
import { GettingStarted } from "../components/guide";
import { DecisionSnapshot } from "../components/insights";
import { analyzeInvestment, loanBalance, monthlyInstalment } from "../utils/finance";
import { compactMoney, displayTitle } from "../utils/format";
import { ClaimBadge, ErrorNote, Loadable } from "../components/ui";
import { AuthProvider, useAuth } from "../hooks/useAuth";
import { navItemsFor } from "../layouts/AppLayout";
import { loginSchema, registerSchema } from "../pages/AuthPages";
import { BlockchainPage } from "../pages/BlockchainPages";
import { propertySchema } from "../pages/PropertyFormPage";
import { ScenarioForm, SimulationResult, scenarioSchema } from "../pages/TwinPages";
import { api, refreshSession } from "../services/api";
import { Route, Routes } from "react-router-dom";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, refreshSession: vi.fn(() => Promise.reject(new Error("no session"))) };
});

const USER = { id: "u1", email: "a@example.com", display_name: "Asha", roles: ["owner"], wallet_address: null, email_verified_at: null, phone: null };
const SESSION = { access_token: "token", user: USER };
const EMPTY_DASHBOARD = {
  roles: ["owner"], properties_accessible: 0, active_twins: 0, pending_verifications: 0, saved_properties: 0, latest_valuations: [], valuation_trend: [], recent_simulations: [], recent_transactions: [],
  model: { available: false, version: null, trained_on_synthetic_data: null, trained_at: null },
  data_freshness: { latest_market_period: null, market_data_is_synthetic: null, last_valuation_at: null },
};
const VALID_PROPERTY = { title: "Flat", property_type: "apartment", address_line1: "1 Road", city: "C", state: "S", postal_code: "500001", listing_status: "draft" };

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.spyOn(api.notifications, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
  vi.spyOn(api.auth, "demoAccounts").mockResolvedValue([]);
  vi.spyOn(api.market, "localities").mockResolvedValue({ localities: [], cities: [], latest_period: null, any_synthetic: false });
});

describe("form validation schemas", () => {
  it("registration needs a valid email, a long password, and matching confirmation", () => {
    const good = { display_name: "A", email: "a@example.com", role: "owner", password: "long-enough-password", confirm: "long-enough-password" };
    expect(registerSchema.safeParse(good).success).toBe(true);
    expect(registerSchema.safeParse({ ...good, email: "nope" }).success).toBe(false);
    expect(registerSchema.safeParse({ ...good, password: "short", confirm: "short" }).success).toBe(false);
    expect(registerSchema.safeParse({ ...good, confirm: "different-password" }).success).toBe(false);
  });

  it("registration offers no privileged roles", () => {
    const base = { display_name: "A", email: "a@example.com", password: "long-enough-password", confirm: "long-enough-password" };
    expect(registerSchema.safeParse({ ...base, role: "admin" }).success).toBe(false);
    expect(registerSchema.safeParse({ ...base, role: "verifier" }).success).toBe(false);
  });

  it("login requires both fields", () => {
    expect(loginSchema.safeParse({ email: "a@example.com", password: "" }).success).toBe(false);
  });

  it("property form rejects bad numbers and treats blanks as missing", () => {
    expect(propertySchema.safeParse(VALID_PROPERTY).success).toBe(true);
    expect(propertySchema.safeParse({ ...VALID_PROPERTY, built_up_area_sqft: "", bedrooms: "" }).success).toBe(true);
    expect(propertySchema.safeParse({ ...VALID_PROPERTY, built_up_area_sqft: "-5" }).success).toBe(false);
    expect(propertySchema.safeParse({ ...VALID_PROPERTY, construction_year: "1500" }).success).toBe(false);
    expect(propertySchema.safeParse({ ...VALID_PROPERTY, floor_number: "9", total_floors: "3" }).success).toBe(false);
  });

  it("scenario form rejects out-of-range values and double counting a renovation", () => {
    const base = { name: "S", market_change_pct: 0, renovation_value_uplift_pct: 0, monthly_rent_change_pct: 0, maintenance_change_pct: 0 };
    expect(scenarioSchema.safeParse(base).success).toBe(true);
    expect(scenarioSchema.safeParse({ ...base, market_change_pct: -95 }).success).toBe(false);
    expect(scenarioSchema.safeParse({ ...base, condition_after: "excellent", renovation_value_uplift_pct: 5 }).success).toBe(false);
  });
});

describe("authentication flow", () => {
  it("shows field errors without calling the API", async () => {
    const login = vi.spyOn(api.auth, "login");
    renderApp("/login");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("signs in and lands on a dashboard filled from the API", async () => {
    vi.spyOn(api.auth, "login").mockResolvedValue(SESSION);
    vi.spyOn(api, "dashboard").mockResolvedValue(EMPTY_DASHBOARD);
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Welcome, Asha")).toBeInTheDocument();
    expect(api.auth.login).toHaveBeenCalledWith({ email: "a@example.com", password: "correct-horse-battery" });
  });

  it("shows the server's error when sign-in fails", async () => {
    vi.spyOn(api.auth, "login").mockRejectedValue(Object.assign(new Error("Invalid email or password."), { status: 401 }));
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("sends a signed-out visitor from a protected page to sign in", async () => {
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("registration never submits the confirmation field", async () => {
    vi.spyOn(api.auth, "register").mockResolvedValue(SESSION);
    vi.spyOn(api, "dashboard").mockResolvedValue(EMPTY_DASHBOARD);
    renderApp("/register");
    await userEvent.type(screen.getByLabelText("Your name"), "Asha");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "long-enough-password");
    await userEvent.type(screen.getByLabelText("Confirm password"), "long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await screen.findByText("Welcome, Asha");
    expect(api.auth.register).toHaveBeenCalledWith({ display_name: "Asha", email: "a@example.com", role: "owner", password: "long-enough-password" });
  });
});

describe("restoring a session on page load", () => {
  function Who() {
    const { user, loading } = useAuth();
    return <p>{loading ? "loading" : user ? `signed in as ${user.display_name}` : "signed out"}</p>;
  }
  const renderWho = () => render(<AuthProvider><Who /></AuthProvider>);
  const failure = (status) => Object.assign(new Error("failed"), { response: { status } });

  beforeEach(() => {
    localStorage.setItem("proptwin_has_session", "1");
  });

  it("restores the user from the refresh cookie", async () => {
    vi.mocked(refreshSession).mockResolvedValueOnce(SESSION);
    renderWho();
    expect(await screen.findByText("signed in as Asha")).toBeInTheDocument();
  });

  it("a page does not request its data until the session is restored", async () => {
    let finishRestore;
    vi.mocked(refreshSession).mockReturnValueOnce(new Promise((resolve) => (finishRestore = resolve)));
    const get = vi.spyOn(api.properties, "get").mockResolvedValue({
      id: "p1", title: "My private draft", owner_id: "u1", access_level: "full", address_line1: "1 Road", postal_code: "1", images: [], renovations: [], amenities: [], listing_status: "draft", verification_status: "unverified", property_type: "apartment", currency: "INR", is_demo: false, property_age: null, floor_number: null,
    });
    vi.spyOn(api.properties, "valuations").mockResolvedValue([]);
    vi.spyOn(api.properties, "documents").mockResolvedValue([]);
    vi.spyOn(api.properties, "verificationHistory").mockResolvedValue([]);
    vi.spyOn(api.twins, "forProperty").mockResolvedValue(null);
    vi.spyOn(api.chain, "record").mockResolvedValue(null);
    renderApp("/properties/p1");
    expect(await screen.findByText(/Restoring your session/)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
    finishRestore(SESSION);
    expect(await screen.findByRole("heading", { name: "My private draft" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit" })).toBeInTheDocument();
  });

  it("a 401 ends the session", async () => {
    vi.mocked(refreshSession).mockRejectedValueOnce(failure(401));
    renderWho();
    expect(await screen.findByText("signed out")).toBeInTheDocument();
    expect(localStorage.getItem("proptwin_has_session")).toBeNull();
  });

  it("a rate limit is retried and does not sign the user out", async () => {
    vi.mocked(refreshSession).mockRejectedValueOnce(failure(429)).mockResolvedValueOnce(SESSION);
    renderWho();
    expect(await screen.findByText("signed in as Asha", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(localStorage.getItem("proptwin_has_session")).toBe("1");
  });

  it("a lasting outage keeps the session for a later attempt", async () => {
    vi.mocked(refreshSession).mockRejectedValue(failure(503));
    renderWho();
    expect(await screen.findByText("signed out", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(localStorage.getItem("proptwin_has_session")).toBe("1");
    vi.mocked(refreshSession).mockReset();
    vi.mocked(refreshSession).mockRejectedValue(new Error("no session"));
  });
});

describe("role-based navigation", () => {
  const labels = (roles) => navItemsFor(roles ? { roles } : null).map((item) => item.label);

  it("guests see only public links", () => {
    expect(labels(null)).toEqual(["Properties", "Market insights", "Investment calculator", "Help center"]);
  });

  it("each role sees its own tools and not others'", () => {
    expect(labels(["owner"])).toContain("My properties");
    expect(labels(["owner"])).not.toContain("Administration");
    expect(labels(["owner"])).not.toContain("Verification");
    expect(labels(["investor"])).toContain("Investments");
    expect(labels(["investor"])).not.toContain("My properties");
    expect(labels(["verifier"])).toContain("Verification");
    expect(labels(["verifier"])).not.toContain("Scenario simulator");
    expect(labels(["admin"])).toEqual(expect.arrayContaining(["Administration", "Verification", "My properties"]));
  });

  it("a direct visit to a page for another role is refused", async () => {
    vi.spyOn(api.auth, "login").mockResolvedValue(SESSION);
    function Harness() {
      const { login, user } = useAuth();
      return user ? <AppRoutes /> : <button onClick={() => login({})}>go</button>;
    }
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <AuthProvider>
          <Harness />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByText("go"));
    expect(await screen.findByText("You do not have access to this page")).toBeInTheDocument();
  });
});

describe("property creation", () => {
  it("submits exact decimal strings, and turns blanks into nulls", async () => {
    vi.spyOn(api.auth, "login").mockResolvedValue(SESSION);
    const create = vi.spyOn(api.properties, "create").mockResolvedValue({ id: "p1" });
    vi.spyOn(api.properties, "get").mockResolvedValue(new Promise(() => {}));
    function Harness() {
      const { login, user } = useAuth();
      return user ? <AppRoutes /> : <button onClick={() => login({})}>go</button>;
    }
    render(
      <MemoryRouter initialEntries={["/properties/new"]}>
        <AuthProvider>
          <Harness />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByText("go"));
    await userEvent.type(await screen.findByLabelText("Title"), "New flat");
    await userEvent.type(screen.getByLabelText("Street address"), "1 Road");
    await userEvent.type(screen.getByLabelText("City"), "Metro");
    await userEvent.type(screen.getByLabelText("State"), "State");
    await userEvent.type(screen.getByLabelText("Postal code"), "500001");
    await userEvent.type(screen.getByLabelText("Built-up area (sq ft)"), "1250.5");
    await userEvent.type(screen.getByLabelText("Amenities"), "gym, pool");
    await userEvent.click(screen.getByRole("button", { name: "Register property" }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    const body = create.mock.calls[0][0];
    expect(body.built_up_area_sqft).toBe("1250.50");
    expect(body.bedrooms).toBeNull();
    expect(body.amenities).toEqual(["gym", "pool"]);
  });
});

const VALUATION = {
  predicted_value: "8450000.00", currency: "INR", interval: { lower: "7200000.00", upper: "9900000.00", nominal_coverage: "0.900" }, predicted_at: "2026-11-05T10:00:00Z", model_version: "v1",
  factors: [{ factor: "Built-up area", effect: "2100000.00", direction: "raises" }], historical_comparison: { previous_value: "8000000.00", previous_valued_at: "2026-10-01T10:00:00Z", change_from_previous_pct: "5.63" },
  trained_on_synthetic_data: true, limitations: ["This model was trained on synthetic demo data."], disclaimer: "It is not a guaranteed sale price or a certified appraisal.",
};

describe("valuation display", () => {
  it("shows the estimate with its range, label, model, disclaimer and limits", () => {
    render(<MemoryRouter><ValuationResult valuation={VALUATION} /></MemoryRouter>);
    expect(screen.getByTestId("predicted-value")).toHaveTextContent("84,50,000");
    expect(screen.getByText(/90% range/)).toHaveTextContent("72,00,000");
    expect(screen.getByText("AI estimate")).toBeInTheDocument();
    expect(screen.getByText("Synthetic demo data")).toBeInTheDocument();
    expect(screen.getByText(/Model v1/)).toBeInTheDocument();
    expect(screen.getByText(/not a guaranteed sale price/)).toBeInTheDocument();
    expect(screen.getByText("This model was trained on synthetic demo data.")).toBeInTheDocument();
  });

  it("hides the synthetic label for a model trained on real data", () => {
    render(<MemoryRouter><ValuationResult valuation={{ ...VALUATION, trained_on_synthetic_data: false, limitations: [] }} /></MemoryRouter>);
    expect(screen.queryByText("Synthetic demo data")).not.toBeInTheDocument();
  });

  it("the unavailable model state shows a message, never a number", async () => {
    vi.spyOn(api.auth, "login").mockResolvedValue(SESSION);
    vi.spyOn(api.properties, "mine").mockResolvedValue({ items: [] });
    vi.spyOn(api.valuations, "predict").mockRejectedValue(Object.assign(new Error("No approved valuation model is active. No estimate has been produced."), { status: 503, code: "model_unavailable" }));
    function Harness() {
      const { login, user } = useAuth();
      return user ? <AppRoutes /> : <button onClick={() => login({})}>go</button>;
    }
    render(
      <MemoryRouter initialEntries={["/valuations"]}>
        <AuthProvider>
          <Harness />
        </AuthProvider>
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByText("go"));
    await userEvent.type(await screen.findByLabelText("Built-up area (sq ft)"), "1000");
    const manual = screen.getByRole("heading", { name: "Or enter details" }).closest("section");
    await userEvent.click(within(manual).getByRole("button", { name: "Predict valuation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No estimate has been produced");
    expect(screen.queryByTestId("predicted-value")).not.toBeInTheDocument();
  });
});

const RUN = {
  id: "r1", name: "Up 5%", method: "formula", calculation_note: "Hypothetical arithmetic, not a new model prediction.", baseline_value: "8000000.00", scenario_value: "8400000.00", absolute_difference: "400000.00", percentage_difference: "5.0000",
  annual_rental_income: null, rental_yield_pct: null, annual_maintenance_cost: null, limitations: ["This is a hypothetical calculation from the stated assumptions, not a forecast of what will happen."], assumptions: [{ name: "market_change_pct", value: "5", unit: "percent" }], created_at: "2026-11-05T10:00:00Z",
};

describe("simulation results", () => {
  it("labels the result as hypothetical and shows how it was calculated", () => {
    render(<SimulationResult run={RUN} />);
    expect(screen.getByText("Hypothetical simulation")).toBeInTheDocument();
    expect(screen.getByText("How this was calculated: a formula")).toBeInTheDocument();
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
    expect(screen.getByText(/not a forecast/)).toBeInTheDocument();
    expect(screen.getAllByText("Not calculated").length).toBe(3);
  });

  it("says so when the model was really rerun", () => {
    render(<SimulationResult run={{ ...RUN, method: "model_rerun" }} />);
    expect(screen.getByText("How this was calculated: the model was rerun")).toBeInTheDocument();
  });

  it("the form sends percentages as strings, using a preset", async () => {
    const simulate = vi.spyOn(api.twins, "simulate").mockResolvedValue(RUN);
    const onResult = vi.fn();
    render(<ScenarioForm twinId="t1" onResult={onResult} />);
    await userEvent.click(screen.getByRole("button", { name: "Market -10%" }));
    await userEvent.click(screen.getByRole("button", { name: "Run scenario" }));
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(RUN));
    expect(simulate.mock.calls[0][1]).toMatchObject({ name: "Market down 10%", market_change_pct: "-10" });
  });
});

const CHAIN_HISTORY = {
  legal_note: "It does not establish legal ownership.",
  record: { property_key: "0xkey", record_hash: "0xhash", record_version: 1, network: "hardhat-local", contract_address: "0xcontract", controller_address: "0xcontroller" },
  transactions: [{ id: "tx1", operation: "register", status: "confirmed", tx_hash: "0x" + "a".repeat(64), block_number: 7, events: [{ event_name: "PropertyRegistered" }], created_at: "2026-11-05T10:00:00Z" }],
};

function renderBlockchainPage() {
  vi.spyOn(api.auth, "login").mockResolvedValue(SESSION);
  function Harness() {
    const { login, user } = useAuth();
    return user ? (
      <Routes>
        <Route path="/properties/:id/blockchain" element={<BlockchainPage />} />
      </Routes>
    ) : (
      <button onClick={() => login({})}>go</button>
    );
  }
  render(
    <MemoryRouter initialEntries={["/properties/p1/blockchain"]}>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </MemoryRouter>,
  );
  return userEvent.click(screen.getByText("go"));
}

describe("blockchain status display", () => {
  beforeEach(() => {
    vi.spyOn(api.properties, "get").mockResolvedValue({ id: "p1", title: "Flat", owner_id: "u1" });
    vi.spyOn(api.chain, "network").mockResolvedValue({ reachable: true });
  });

  it("shows the record, its history, and the legal note", async () => {
    vi.spyOn(api.chain, "history").mockResolvedValue(CHAIN_HISTORY);
    await renderBlockchainPage();
    expect(await screen.findByText("0xhash")).toBeInTheDocument();
    expect(screen.getByText("PropertyRegistered")).toBeInTheDocument();
    expect(screen.getByText("It does not establish legal ownership.")).toBeInTheDocument();
    expect(screen.getByText(/Controlling a wallet is not legal ownership/)).toBeInTheDocument();
  });

  it("a submitted transaction is not presented as confirmed", async () => {
    vi.spyOn(api.chain, "history").mockResolvedValue({ ...CHAIN_HISTORY, record: null, transactions: [] });
    vi.spyOn(api.chain, "register").mockResolvedValue({ id: "tx2", status: "submitted", confirmations: 0, required_confirmations: 1 });
    vi.spyOn(api.chain, "transaction").mockReturnValue(new Promise(() => {}));
    await renderBlockchainPage();
    await userEvent.click(await screen.findByRole("button", { name: "Register on blockchain" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Submit transaction" }));
    expect(await screen.findByText(/It is not confirmed yet/)).toBeInTheDocument();
    expect(screen.queryByText(/Confirmed in block/)).not.toBeInTheDocument();
  });

  it("a failed transaction shows its reason", async () => {
    vi.spyOn(api.chain, "history").mockResolvedValue({ ...CHAIN_HISTORY, record: null, transactions: [] });
    vi.spyOn(api.chain, "register").mockResolvedValue({ id: "tx3", status: "failed", failure_reason: "The blockchain node is unreachable", confirmations: 0, required_confirmations: 1 });
    await renderBlockchainPage();
    await userEvent.click(await screen.findByRole("button", { name: "Register on blockchain" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Submit transaction" }));
    expect(await screen.findByText(/The blockchain node is unreachable/)).toBeInTheDocument();
  });

  it("reports a mismatch and names the fields", async () => {
    vi.spyOn(api.chain, "history").mockResolvedValue(CHAIN_HISTORY);
    vi.spyOn(api.chain, "verify").mockResolvedValue({ result: "mismatch", matches: false, detail: "It differs.", changed_fields: ["last_sale_price"], covered_fields: [], hash_version: 1, checked_at: "2026-11-05T10:00:00Z" });
    await renderBlockchainPage();
    await userEvent.click(await screen.findByRole("button", { name: "Check record integrity" }));
    const result = await screen.findByTestId("integrity-result");
    expect(result).toHaveAttribute("data-result", "mismatch");
    expect(result).toHaveTextContent("Last sale price");
  });
});

describe("chart axis", () => {
  it("a single point gets a range wide enough for distinct tick labels", () => {
    const [low, high] = paddedDomain([10601717]);
    expect(low).toBeLessThan(10601717);
    expect(high).toBeGreaterThan(10601717);
    expect(compactMoney(low)).not.toBe(compactMoney(high));
  });

  it("a varied series keeps its full range", () => {
    const [low, high] = paddedDomain([100, 200]);
    expect(low).toBeLessThan(100);
    expect(high).toBeGreaterThan(200);
  });
});

describe("assumptions list", () => {
  it("does not list values the user left at zero", () => {
    render(<SimulationResult run={{ ...RUN, assumptions: [{ name: "market_change_pct", value: "5", unit: "percent" }, { name: "maintenance_change_pct", value: "0", unit: "percent" }] }} />);
    expect(screen.getByText(/Market change pct/)).toBeInTheDocument();
    expect(screen.queryByText(/Maintenance change pct/)).not.toBeInTheDocument();
  });
});

describe("loading and error states", () => {
  it("Loadable shows progress, then errors with a retry, then content", async () => {
    const retry = vi.fn();
    const { rerender } = render(<Loadable state={{ loading: true, data: null, error: null }}>{() => <p>content</p>}</Loadable>);
    expect(screen.getByRole("status")).toBeInTheDocument();
    rerender(<Loadable state={{ loading: false, data: null, error: new Error("It broke"), reload: retry }}>{() => <p>content</p>}</Loadable>);
    expect(screen.getByRole("alert")).toHaveTextContent("It broke");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
    rerender(<Loadable state={{ loading: false, data: {}, error: null }}>{() => <p>content</p>}</Loadable>);
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("listing page shows an empty state when nothing matches", async () => {
    vi.spyOn(api.properties, "search").mockResolvedValue({ items: [], page: 1, page_size: 12, total: 0 });
    renderApp("/properties");
    expect(await screen.findByText("No properties match")).toBeInTheDocument();
  });

  it("listing page shows an error when the API fails", async () => {
    vi.spyOn(api.properties, "search").mockRejectedValue(new Error("Could not reach the server."));
    renderApp("/properties");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("unknown routes show the not-found page", async () => {
    renderApp("/no/such/page");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });

  it("server field errors are listed", () => {
    render(<ErrorNote error={Object.assign(new Error("The request is invalid."), { fields: [{ field: "title", message: "Too short" }] })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("title: Too short");
  });

  it("the four kinds of claim are visually distinct and named", () => {
    render(<>{["ai", "hypothetical", "document", "chain"].map((kind) => <ClaimBadge key={kind} kind={kind} />)}</>);
    for (const name of ["AI estimate", "Hypothetical simulation", "Verifier decision", "Blockchain-confirmed"]) expect(screen.getByText(name)).toBeInTheDocument();
  });
});

describe("investment arithmetic", () => {
  it("matches a known instalment, and handles a zero rate", () => {
    // 10,00,000 at 12% for 10 years is a standard worked example: 14,347.09 a month.
    expect(monthlyInstalment(1000000, 12, 10)).toBeCloseTo(14347.09, 1);
    expect(monthlyInstalment(1200000, 0, 10)).toBe(10000);
    expect(monthlyInstalment(0, 8, 20)).toBe(0);
  });

  it("the loan balance starts at the principal and reaches zero", () => {
    expect(loanBalance(1000000, 9, 20, 0)).toBeCloseTo(1000000, 4);
    expect(loanBalance(1000000, 9, 20, 20)).toBe(0);
    expect(loanBalance(1000000, 9, 20, 10)).toBeLessThan(1000000);
    expect(loanBalance(1200000, 0, 10, 5)).toBeCloseTo(600000, 4);
  });

  const BASE = { price: 10000000, downPaymentPct: 20, closingCostPct: 5, interestRatePct: 9, loanYears: 20, monthlyRent: 50000, vacancyPct: 10, annualCosts: 60000, appreciationPct: 5, holdYears: 10 };

  it("derives yield, cap rate and cash from stated assumptions", () => {
    const result = analyzeInvestment(BASE);
    expect(result.loan).toBe(8000000);
    expect(result.cashInvested).toBe(2500000);
    expect(result.grossYieldPct).toBeCloseTo(6, 6);
    // 6,00,000 of rent, less 10% vacancy, less 60,000 of costs: 4,80,000 on 1 crore.
    expect(result.capRatePct).toBeCloseTo(4.8, 6);
    expect(result.projection).toHaveLength(11);
    expect(result.projection[0].equity).toBeCloseTo(2000000, 2);
  });

  it("at the break-even rent, cash flow is zero", () => {
    const { breakEvenRent } = analyzeInvestment(BASE);
    expect(analyzeInvestment({ ...BASE, monthlyRent: breakEvenRent }).annualCashFlow).toBeCloseTo(0, 4);
  });

  it("a cash purchase has no debt figures, and full vacancy has no break-even rent", () => {
    const cash = analyzeInvestment({ ...BASE, downPaymentPct: 100 });
    expect(cash.instalment).toBe(0);
    expect(cash.debtCoverage).toBeNull();
    expect(analyzeInvestment({ ...BASE, vacancyPct: 100 }).breakEvenRent).toBeNull();
  });
});

describe("getting started checklist", () => {
  const ONBOARDING = {
    role: "owner",
    completed: 1,
    total: 2,
    steps: [
      { key: "register", title: "Register a property", description: "Record it.", done: true, href: "/properties/new", cta: "Register a property" },
      { key: "estimate", title: "Get an AI estimate", description: "See a value.", done: false, href: "/valuations?property=p1", cta: "Get an estimate" },
    ],
  };
  const show = (onboarding) => render(<MemoryRouter><GettingStarted onboarding={onboarding} /></MemoryRouter>);
  beforeEach(() => localStorage.clear());

  it("shows progress and links only the next step", () => {
    show(ONBOARDING);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("1 of 2 done")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get an estimate" })).toHaveAttribute("href", "/valuations?property=p1");
    expect(screen.queryByRole("link", { name: "Register a property" })).not.toBeInTheDocument();
  });

  it("stays hidden once dismissed", async () => {
    const { unmount } = show(ONBOARDING);
    await userEvent.click(screen.getByRole("button", { name: "Hide getting started" }));
    expect(screen.queryByText("Getting started")).not.toBeInTheDocument();
    unmount();
    show(ONBOARDING);
    expect(screen.queryByText("Getting started")).not.toBeInTheDocument();
  });

  it("renders nothing when the API sends no checklist", () => {
    const { container } = show(undefined);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("decision snapshot", () => {
  const INSIGHTS = {
    currency: "INR", asking_price: "9000000.00", asking_per_sqft: "9000.00", market_per_sqft: "6000.00", premium_to_market_pct: "50.00", gross_yield_pct: "4.00", market_yield_pct: "3.50",
    market: { locality: "Riverside", latest_period: "2026-11-01", change_12m_pct: "6.20", cagr_5y_pct: "5.10", is_synthetic: true },
    estimate: { value: "8000000.00", lower: "7000000.00", upper: "8500000.00", predicted_at: "2026-11-05T00:00:00Z", model_version: "v1", trained_on_synthetic_data: true, is_current: false },
    price_position: "above_range", asking_vs_estimate_pct: "12.50",
    status: { has_estimate: true, estimate_current: false, has_twin: false, verification_status: "unverified", on_chain: false },
    takeaways: [{ tone: "caution", text: "The asking price is 12.50% above the AI estimate and outside its range." }],
    completeness: null, disclaimer: "These comparisons are arithmetic.",
  };
  const show = (insights) => render(<MemoryRouter><DecisionSnapshot insights={insights} propertyId="p1" signedIn /></MemoryRouter>);

  it("states the price position in words, with its labels and disclaimer", () => {
    show(INSIGHTS);
    expect(screen.getByText("Above the estimate's range")).toBeInTheDocument();
    expect(screen.getByText("AI estimate")).toBeInTheDocument();
    expect(screen.getByText("Synthetic demo data")).toBeInTheDocument();
    expect(screen.getByText(/out of date/)).toBeInTheDocument();
    expect(screen.getByText("These comparisons are arithmetic.")).toBeInTheDocument();
    expect(screen.getByText(/Locality median/)).toHaveTextContent("6,000");
  });

  it("with no estimate it shows no figure, and offers to get one", () => {
    show({ ...INSIGHTS, estimate: null, price_position: null, asking_vs_estimate_pct: null });
    expect(screen.getByText(/No estimate has been made/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get one now" })).toHaveAttribute("href", "/valuations?property=p1");
    expect(screen.queryByText("Range low")).not.toBeInTheDocument();
  });
});

describe("demo access", () => {
  it("offers no demo sign-in when the API lists no accounts", async () => {
    vi.spyOn(api.auth, "demoAccounts").mockResolvedValue([]);
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    await waitFor(() => expect(api.auth.demoAccounts).toHaveBeenCalled());
    expect(screen.queryByText(/Explore as/)).not.toBeInTheDocument();
  });

  it("opens a demo account with one click, and says it is a demo", async () => {
    vi.spyOn(api.auth, "demoAccounts").mockResolvedValue([{ email: "demo.owner@proptwin.example", display_name: "Demo Owner", roles: ["owner"] }]);
    vi.spyOn(api.auth, "demoLogin").mockResolvedValue({ access_token: "t", user: { ...USER, display_name: "Demo Owner", is_demo: true } });
    vi.spyOn(api, "dashboard").mockResolvedValue(EMPTY_DASHBOARD);
    vi.spyOn(api.market, "localities").mockResolvedValue({ localities: [], cities: [], latest_period: null, any_synthetic: false });
    renderApp("/login");
    await userEvent.click(await screen.findByRole("button", { name: /Explore as Property owner/ }));
    expect(await screen.findByText("Welcome, Demo Owner")).toBeInTheDocument();
    expect(api.auth.demoLogin).toHaveBeenCalledWith("demo.owner@proptwin.example");
    expect(screen.getByText(/exploring a demo account/)).toBeInTheDocument();
  });
});

describe("chart ticks", () => {
  const evenly = (ticks) => new Set(ticks.slice(1).map((tick, index) => Number((tick - ticks[index]).toFixed(4)))).size === 1;

  it("are round, evenly spaced, and cover the data", () => {
    for (const values of [[961000, 9825000], [82, 277], [100, 100], [1.2, 1.9], [12400000]]) {
      const ticks = niceTicks(values);
      expect(evenly(ticks)).toBe(true);
      expect(ticks[0]).toBeLessThanOrEqual(Math.min(...values));
      expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(Math.max(...values));
      expect(ticks.length).toBeLessThanOrEqual(8);
    }
  });

  it("stay above zero for positive data, and can go below it otherwise", () => {
    expect(niceTicks([1, 1000])[0]).toBe(0);
    expect(niceTicks([-500000, 1000000])[0]).toBeLessThan(0);
  });
});

describe("demo titles", () => {
  it("drops the prefix from demo records only", () => {
    expect(displayTitle({ is_demo: true, title: "[DEMO] Villa #3" })).toBe("Villa #3");
    expect(displayTitle({ is_demo: false, title: "[DEMO] Villa #3" })).toBe("[DEMO] Villa #3");
  });
});
