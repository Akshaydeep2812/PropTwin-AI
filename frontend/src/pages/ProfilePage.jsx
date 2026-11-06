import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Badge, Button, Card, DataTable, Empty, ErrorNote, Loadable, Notice, PageHeader, SuccessNote, TextField } from "../components/ui";
import { useAction, useAsync } from "../hooks/useAsync";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { connectWallet, signMessage, walletAvailable } from "../services/wallet";
import { dateTime } from "../utils/format";

function ProfileForm() {
  const { user, setUser } = useAuth();
  const [saved, setSaved] = useState(false);
  const { register, handleSubmit } = useForm({ defaultValues: { display_name: user.display_name, phone: user.phone ?? "" } });
  const save = useAction(async (values) => {
    setSaved(false);
    setUser(await api.users.update(values));
    setSaved(true);
  });
  return (
    <Card title="Profile">
      <form onSubmit={handleSubmit((values) => save.run(values))} className="space-y-3">
        <ErrorNote error={save.error} />
        {saved && <SuccessNote>Profile saved.</SuccessNote>}
        <TextField label="Name" registration={register("display_name", { required: true })} />
        <TextField label="Phone" registration={register("phone")} />
        <p className="text-sm text-slate-600">
          Email: {user.email} <Badge tone={user.email_verified_at ? "teal" : "amber"}>{user.email_verified_at ? "Verified" : "Not verified"}</Badge>
        </p>
        <p className="text-sm text-slate-600">Roles: {user.roles.join(", ")}</p>
        <Button type="submit" busy={save.busy}>
          Save
        </Button>
      </form>
    </Card>
  );
}

function EmailVerification() {
  const { user } = useAuth();
  const [message, setMessage] = useState(null);
  const send = useAction(async () => setMessage(await api.auth.requestEmailVerification()));
  if (user.email_verified_at) return null;
  return (
    <Card title="Verify your email">
      <ErrorNote error={send.error} />
      {message && <Notice tone={message.delivery === "sent" ? "success" : "warning"}>{message.message}</Notice>}
      <Button variant="secondary" className="mt-2" busy={send.busy} onClick={() => send.run()}>
        Send verification email
      </Button>
    </Card>
  );
}

function PasswordForm() {
  const [done, setDone] = useState(null);
  const { register, handleSubmit, reset, formState } = useForm();
  const change = useAction(async (values) => {
    setDone((await api.users.changePassword(values)).message);
    reset();
  });
  return (
    <Card title="Change password">
      <form onSubmit={handleSubmit((values) => change.run(values))} noValidate className="space-y-3">
        <ErrorNote error={change.error} />
        {done && <SuccessNote>{done}</SuccessNote>}
        <TextField label="Current password" type="password" autoComplete="current-password" registration={register("current_password", { required: "Enter your current password." })} error={formState.errors.current_password?.message} />
        <TextField label="New password" type="password" autoComplete="new-password" registration={register("new_password", { required: "Enter a new password.", minLength: { value: 12, message: "Use at least 12 characters." } })} error={formState.errors.new_password?.message} />
        <Button type="submit" busy={change.busy}>
          Change password
        </Button>
      </form>
    </Card>
  );
}

function WalletCard() {
  const { user, setUser } = useAuth();
  const link = useAction(async () => {
    const address = await connectWallet();
    const { message } = await api.users.walletChallenge(address);
    const signature = await signMessage(address, message);
    setUser(await api.users.linkWallet({ address, signature }));
  });
  return (
    <Card title="Wallet">
      <p className="mb-3 text-sm text-slate-600">Linking proves you control this wallet. It does not prove you own any property. This application never sees your private key.</p>
      {user.wallet_address && <p className="mb-3 break-all font-mono text-xs text-navy-900">{user.wallet_address}</p>}
      <ErrorNote error={link.error} />
      {walletAvailable() ? (
        <Button variant="secondary" className="mt-2" busy={link.busy} onClick={() => link.run()}>
          {user.wallet_address ? "Link a different wallet" : "Connect and link wallet"}
        </Button>
      ) : (
        <Notice>No browser wallet was detected. Install one, such as MetaMask, to link it. Properties can still be registered without one.</Notice>
      )}
    </Card>
  );
}

function Notifications() {
  const state = useAsync(() => api.notifications.list({ page_size: 20 }), []);
  const read = useAction(async (id) => {
    await api.notifications.markRead(id);
    state.reload();
  });
  return (
    <div id="notifications">
      <Card title="Notifications">
        <ErrorNote error={read.error} />
        <Loadable state={state} label="Loading notifications">
          {(data) => (
            <DataTable
              rows={data.items}
              rowKey={(row) => row.id}
              empty={<Empty title="No notifications" />}
              columns={[
                { header: "Message", cell: (row) => <>{row.link ? <Link className={`text-teal-700 underline ${row.read_at ? "" : "font-semibold"}`} to={row.link}>{row.title}</Link> : <span className={row.read_at ? "" : "font-semibold"}>{row.title}</span>}{row.body && <p className="break-all text-xs text-slate-500">{row.body}</p>}</> },
                { header: "When", cell: (row) => dateTime(row.created_at) },
                { header: "", cell: (row) => (row.read_at ? <span className="text-xs text-slate-500">Read</span> : <button type="button" className="text-xs font-medium text-teal-700 underline" onClick={() => read.run(row.id)}>Mark read</button>) },
              ]}
            />
          )}
        </Loadable>
      </Card>
    </div>
  );
}

function Sessions() {
  const { logout } = useAuth();
  const everywhere = useAction(async () => {
    await api.auth.logoutAll();
    await logout();
  });
  return (
    <Card title="Sessions">
      <ErrorNote error={everywhere.error} />
      <p className="mb-3 text-sm text-slate-600">Sign out on every device, including this one.</p>
      <Button variant="secondary" busy={everywhere.busy} onClick={() => everywhere.run()}>
        Sign out everywhere
      </Button>
    </Card>
  );
}

export default function ProfilePage() {
  return (
    <>
      <PageHeader title="Profile and settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <ProfileForm />
          <EmailVerification />
          <WalletCard />
        </div>
        <div className="space-y-4">
          <PasswordForm />
          <Sessions />
        </div>
        <div className="lg:col-span-2">
          <Notifications />
        </div>
      </div>
    </>
  );
}
