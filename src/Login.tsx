import { useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { supabase } from "./lib/supabase";
import { Logo } from "./Icons";
import { BRAND, LINKS } from "./config";
import { makeT, type Lang } from "./lib/i18n";

/* Client giriş ekranı — web/mobil ile aynı hesap. Giriş sonrası aboneliğe göre profiller açılır.
   FREE_MODE=true iken App bu ekranı atlar (bypass). */
export default function Login({ onDone, lang }: { onDone: () => void; lang: Lang }) {
  const t = makeT(lang);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function mapAuthError(msg: string): string {
    const m = (msg || "").toLowerCase();
    if (m.includes("invalid login")) return t("login.badCreds");
    if (m.includes("email not confirmed")) return t("login.emailNotConfirmed");
    if (m.includes("rate limit") || m.includes("too many")) return t("login.rateLimited");
    return t("login.generic"); // ham İngilizce Supabase metni yerine yerelleştirilmiş genel mesaj
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password: pw });
      if (error) setErr(mapAuthError(error.message));
      else onDone();
    } catch {
      // signInWithPassword bazı ağ hatalarında REJECT eder → "Giriş yapılıyor…"da takılmasın
      setErr(t("login.netErr"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <div className="card p-7">
        <div className="flex flex-col items-center text-center">
          <span className="grid h-12 w-12 place-items-center rounded-xl bg-primary/15 text-primary ring-1 ring-primary/25">
            <Logo className="h-7 w-7" />
          </span>
          <h1 className="mt-4 text-xl font-bold">{BRAND.clientName}</h1>
          <p className="mt-1 text-sm text-muted">{t("login.sub")}</p>
        </div>
        <form onSubmit={submit} className="mt-6 space-y-3">
          <input
            type="email"
            required
            autoFocus
            placeholder={t("login.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-soft px-3.5 py-2.5 text-sm outline-none focus:border-primary/60"
          />
          <input
            type="password"
            required
            placeholder={t("login.password")}
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-soft px-3.5 py-2.5 text-sm outline-none focus:border-primary/60"
          />
          {err && <p className="text-sm text-danger">{err}</p>}
          <button type="submit" disabled={busy} className="btn-primary w-full disabled:opacity-60">
            {busy ? t("login.signingIn") : t("login.signIn")}
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-muted">
          {t("login.noAccount")}{" "}
          <button
            type="button"
            onClick={() => void openUrl(LINKS.website).catch(() => {})}
            className="text-primary hover:underline"
          >
            {t("login.register")}
          </button>
        </p>
      </div>
    </div>
  );
}
