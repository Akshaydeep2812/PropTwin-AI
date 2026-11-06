/**
 * Pure investment arithmetic for the calculator. No dates, randomness or API calls, so the same inputs always give the
 * same answer. Everything here is a hypothetical calculation from assumptions the user can see and change.
 */

export function monthlyInstalment(principal, annualRatePct, years) {
  if (principal <= 0 || years <= 0) return 0;
  const months = years * 12;
  const rate = annualRatePct / 100 / 12;
  if (rate === 0) return principal / months;
  const growth = (1 + rate) ** months;
  return (principal * rate * growth) / (growth - 1);
}

/** What is still owed after a number of years of regular instalments. */
export function loanBalance(principal, annualRatePct, years, afterYears) {
  if (principal <= 0) return 0;
  if (afterYears >= years) return 0;
  const rate = annualRatePct / 100 / 12;
  const paid = afterYears * 12;
  if (rate === 0) return principal * (1 - paid / (years * 12));
  const instalment = monthlyInstalment(principal, annualRatePct, years);
  return principal * (1 + rate) ** paid - (instalment * ((1 + rate) ** paid - 1)) / rate;
}

export function analyzeInvestment({ price, downPaymentPct, closingCostPct, interestRatePct, loanYears, monthlyRent, vacancyPct, annualCosts, appreciationPct, holdYears }) {
  const downPayment = (price * downPaymentPct) / 100;
  const closingCosts = (price * closingCostPct) / 100;
  const loan = Math.max(0, price - downPayment);
  const instalment = monthlyInstalment(loan, interestRatePct, loanYears);
  const annualDebtService = instalment * 12;
  const collectedRent = monthlyRent * 12 * (1 - vacancyPct / 100);
  const netOperatingIncome = collectedRent - annualCosts;
  const annualCashFlow = netOperatingIncome - annualDebtService;
  const cashInvested = downPayment + closingCosts;

  const projection = [];
  for (let year = 0; year <= holdYears; year += 1) {
    const value = price * (1 + appreciationPct / 100) ** year;
    const balance = loanBalance(loan, interestRatePct, loanYears, year);
    projection.push({ year, value, balance, equity: value - balance });
  }

  return {
    downPayment,
    closingCosts,
    cashInvested,
    loan,
    instalment,
    totalInterest: Math.max(0, instalment * loanYears * 12 - loan),
    collectedRent,
    netOperatingIncome,
    annualDebtService,
    annualCashFlow,
    monthlyCashFlow: annualCashFlow / 12,
    grossYieldPct: price > 0 ? (monthlyRent * 12 * 100) / price : null,
    capRatePct: price > 0 ? (netOperatingIncome * 100) / price : null,
    cashOnCashPct: cashInvested > 0 ? (annualCashFlow * 100) / cashInvested : null,
    debtCoverage: annualDebtService > 0 ? netOperatingIncome / annualDebtService : null,
    // The monthly rent at which rent received exactly covers costs and instalments. Null when no rent can ever be collected.
    breakEvenRent: vacancyPct < 100 ? (annualCosts + annualDebtService) / 12 / (1 - vacancyPct / 100) : null,
    projection,
  };
}
