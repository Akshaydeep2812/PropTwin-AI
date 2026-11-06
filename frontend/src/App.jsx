import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./hooks/useAuth";
import AppLayout from "./layouts/AppLayout";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from "./pages/AuthPages";
import { BlockchainPage, TransfersPage } from "./pages/BlockchainPages";
import { AdminDashboardPage, DashboardPage, InvestorDashboardPage, OwnerDashboardPage, VerifierDashboardPage } from "./pages/DashboardPages";
import CalculatorPage from "./pages/CalculatorPage";
import { ErrorBoundary, NotFoundPage } from "./pages/ErrorPages";
import HelpPage from "./pages/HelpPage";
import LandingPage from "./pages/LandingPage";
import MarketPage from "./pages/MarketPage";
import ProfilePage from "./pages/ProfilePage";
import PropertyDetailPage from "./pages/PropertyDetailPage";
import PropertyFormPage from "./pages/PropertyFormPage";
import PropertyListPage from "./pages/PropertyListPage";
import PropertyReportPage from "./pages/PropertyReportPage";
import { SimulatorPage, TwinWorkspacePage } from "./pages/TwinPages";
import { ValuationHistoryPage, ValuationWorkspacePage } from "./pages/ValuationPages";
import { GuestOnly, RequireAuth } from "./routes/guards";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />

      <Route element={<AppLayout />}>
        <Route path="/properties" element={<PropertyListPage />} />
        <Route path="/market" element={<MarketPage />} />
        <Route path="/calculator" element={<CalculatorPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route element={<RequireAuth roles={["owner", "admin"]} />}>
          <Route path="/properties/new" element={<PropertyFormPage />} />
          <Route path="/properties/:id/edit" element={<PropertyFormPage />} />
          <Route path="/owner" element={<OwnerDashboardPage />} />
        </Route>
        <Route path="/properties/:id" element={<PropertyDetailPage />} />
        <Route path="/properties/:id/report" element={<PropertyReportPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/valuations" element={<ValuationWorkspacePage />} />
          <Route path="/valuations/history" element={<ValuationHistoryPage />} />
          <Route path="/properties/:id/twin" element={<TwinWorkspacePage />} />
          <Route path="/properties/:id/blockchain" element={<BlockchainPage />} />
          <Route path="/transfers" element={<TransfersPage />} />
          <Route path="/transfers/:transferId" element={<TransfersPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
        <Route element={<RequireAuth roles={["owner", "investor", "admin"]} />}>
          <Route path="/simulator" element={<SimulatorPage />} />
        </Route>
        <Route element={<RequireAuth roles={["investor"]} />}>
          <Route path="/investor" element={<InvestorDashboardPage />} />
        </Route>
        <Route element={<RequireAuth roles={["verifier", "admin"]} />}>
          <Route path="/verifier" element={<VerifierDashboardPage />} />
        </Route>
        <Route element={<RequireAuth roles={["admin"]} />}>
          <Route path="/admin" element={<AdminDashboardPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
