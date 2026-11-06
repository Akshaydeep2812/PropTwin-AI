import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { CheckCircle2 } from "lucide-react";
import { DemoAccess } from "../components/guide";
import { Button, ErrorNote, SelectField, Spinner, SuccessNote, TextField } from "../components/ui";
import { BrandMark } from "../layouts/AppLayout";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";

const password = z.string().min(12, "Use at least 12 characters.").max(128, "Use at most 128 characters.");
export const registerSchema = z
  .object({
    display_name: z.string().trim().min(1, "Enter your name.").max(120),
    email: z.string().email("Enter a valid email address."),
    role: z.enum(["owner", "investor"]),
    password,
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, { path: ["confirm"], message: "The passwords do not match." });
export const loginSchema = z.object({ email: z.string().email("Enter a valid email address."), password: z.string().min(1, "Enter your password.") });

const AUTH_POINTS = ["An AI estimate and range for any property", "Asking prices checked against the estimate and locality", "Scenarios, return calculations and printable reports", "Verified, tamper-evident records"];

function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1fr_1.1fr]">
      <aside className="hero-backdrop hidden flex-col justify-between p-10 text-white lg:flex">
        <Link to="/" className="flex items-center gap-2.5">
          <BrandMark />
          <span className="font-display text-lg font-medium tracking-tight">PropTwin AI</span>
        </Link>
        <div>
          <p className="font-display max-w-md text-4xl font-medium leading-tight tracking-tight">Know what a property is worth, and how far to trust that number.</p>
          <ul className="mt-6 space-y-2.5 text-sm text-slate-300">
            {AUTH_POINTS.map((point) => (
              <li key={point} className="flex gap-2">
                <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-teal-100" /> {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-400">Valuations are statistical estimates, not appraisals.</p>
      </aside>
      <div className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <Link to="/" className="mb-6 flex items-center gap-2 lg:hidden">
            <BrandMark />
            <span className="font-display text-lg font-medium text-navy-900">PropTwin AI</span>
          </Link>
          <h1 className="text-3xl text-navy-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <p className="mt-6 text-center text-sm text-slate-600">{footer}</p>}
        </div>
      </div>
    </div>
  );
}

const ROLE_DETAILS = {
  owner: "You can register properties, get estimates, create digital twins, run scenarios, request verification and commit records to the blockchain.",
  investor: "You can save and compare listings, check asking prices against AI estimates, run scenarios on listings with twins, and calculate returns.",
};

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState } = useForm({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values) => {
    setError(null);
    try {
      await login(values);
      navigate(location.state?.from ?? "/dashboard", { replace: true });
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <AuthShell
      title="Sign in"
      footer={
        <>
          New here? <Link className="font-medium text-teal-700" to="/register">Create an account</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        <ErrorNote error={error} />
        <TextField label="Email" type="email" autoComplete="email" registration={register("email")} error={formState.errors.email?.message} />
        <TextField label="Password" type="password" autoComplete="current-password" registration={register("password")} error={formState.errors.password?.message} />
        <Button type="submit" busy={formState.isSubmitting} className="w-full">
          Sign in
        </Button>
        <p className="text-center text-sm">
          <Link className="text-teal-700" to="/forgot-password">Forgot your password?</Link>
        </p>
      </form>
      <div className="mt-6 border-t border-slate-200 pt-5">
        <DemoAccess />
      </div>
    </AuthShell>
  );
}

export function RegisterPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState, watch } = useForm({ resolver: zodResolver(registerSchema), defaultValues: { role: "owner" } });
  const role = watch("role");

  const onSubmit = async ({ confirm: _confirm, ...values }) => {
    setError(null);
    try {
      await auth.register(values);
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="Your first steps appear on your dashboard straight after this."
      footer={
        <>
          Already registered? <Link className="font-medium text-teal-700" to="/login">Sign in</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        <ErrorNote error={error} />
        <TextField label="Your name" autoComplete="name" registration={register("display_name")} error={formState.errors.display_name?.message} />
        <TextField label="Email" type="email" autoComplete="email" registration={register("email")} error={formState.errors.email?.message} />
        <SelectField
          label="I want to"
          registration={register("role")}
          options={[
            { value: "owner", label: "Register and manage properties" },
            { value: "investor", label: "Find and compare properties" },
          ]}
          hint="Verifier and administrator access is granted by an administrator."
        />
        <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">{ROLE_DETAILS[role]}</p>
        <TextField label="Password" type="password" autoComplete="new-password" hint="At least 12 characters." registration={register("password")} error={formState.errors.password?.message} />
        <TextField label="Confirm password" type="password" autoComplete="new-password" registration={register("confirm")} error={formState.errors.confirm?.message} />
        <Button type="submit" busy={formState.isSubmitting} className="w-full">
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(null);
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState } = useForm({ resolver: zodResolver(z.object({ email: z.string().email("Enter a valid email address.") })) });

  const onSubmit = async ({ email }) => {
    setError(null);
    try {
      setSent((await api.auth.requestReset(email)).message);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <AuthShell title="Reset your password" footer={<Link className="font-medium text-teal-700" to="/login">Back to sign in</Link>}>
      {sent ? (
        <SuccessNote>{sent}</SuccessNote>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <ErrorNote error={error} />
          <TextField label="Email" type="email" registration={register("email")} error={formState.errors.email?.message} />
          <Button type="submit" busy={formState.isSubmitting} className="w-full">
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState } = useForm({ resolver: zodResolver(z.object({ new_password: password })) });

  const onSubmit = async ({ new_password }) => {
    setError(null);
    try {
      setDone((await api.auth.confirmReset({ token: params.get("token") ?? "", new_password })).message);
    } catch (caught) {
      setError(caught);
    }
  };

  return (
    <AuthShell title="Choose a new password" footer={<Link className="font-medium text-teal-700" to="/login">Back to sign in</Link>}>
      {done ? (
        <SuccessNote>{done}</SuccessNote>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <ErrorNote error={error} />
          <TextField label="New password" type="password" autoComplete="new-password" registration={register("new_password")} error={formState.errors.new_password?.message} />
          <Button type="submit" busy={formState.isSubmitting} className="w-full">
            Update password
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [state, setState] = useState({ loading: true });
  const token = params.get("token") ?? "";

  useEffect(() => {
    api.auth
      .confirmEmail(token)
      .then((result) => setState({ message: result.message }))
      .catch((error) => setState({ error }));
  }, [token]);

  return (
    <AuthShell title="Email verification" footer={<Link className="font-medium text-teal-700" to="/login">Continue to sign in</Link>}>
      {state.loading && <Spinner label="Checking your link" />}
      {state.message && <SuccessNote>{state.message}</SuccessNote>}
      <ErrorNote error={state.error} />
    </AuthShell>
  );
}
