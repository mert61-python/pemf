import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  PROFILES,
  BRAND,
  LINKS,
  FEATURES,
  APP_URL,
  CLIENT_BASE_MB,
  MANIFEST_URL,
  CLIENT_UPDATE_URL,
  FREE_MODE,
} from "./config";
import {
  Logo,
  Check,
  Bolt,
  Download,
  Play,
  Pause,
  Close,
  ArrowRight,
  Sparkle,
  Refresh,
  Lock,
  LogOut,
  Globe,
  Info,
  PROFILE_ICONS,
  FEATURE_ICONS,
} from "./Icons";
import Login from "./Login";
import About from "./About";
import ConfirmModal from "./ConfirmModal";
import MacLauncher from "./MacLauncher";
import { supabase } from "./lib/supabase";
import { fetchEntitlement, allowedProfileIds, type Entitlement } from "./lib/entitlement";
import { makeT, loadLang, saveLang, PROFILE_I18N, type Lang } from "./lib/i18n";
import appPreview from "./assets/app-preview.jpg";

type Step = "loading" | "updating" | "login" | "profiles" | "installing" | "ready";
type InstallProgress = {
  percent: number;
  label: string;
  state: string;
  done: boolean;
  error: string | null;
  downloadedMb: number;
  totalMb: number;
  speedMbps: number;
};
type UpdateInfo = { version: string; sha256: string; notes: string; url: string };

const tl = (n: number) => `₺${n.toLocaleString("tr-TR")}`;
const fmtGb = (mb: number) => (mb / 1024).toFixed(1); // tutarlı tek-ondalık (karışık "0.5 / 2.10 GB" önlendi)

// Self-update deneme debounce: aynı sürüm son 4 saatte denendiyse tekrar deneme (UAC reddi → döngü olmasın).
const UPD_KEY = "pemf-client-update-attempt";
function recentlyAttempted(v: string): boolean {
  try {
    const raw = localStorage.getItem(UPD_KEY);
    if (!raw) return false;
    const o = JSON.parse(raw) as { version?: string; at?: number };
    return o.version === v && typeof o.at === "number" && Date.now() - o.at < 4 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}
function markAttempt(v: string) {
  try {
    localStorage.setItem(UPD_KEY, JSON.stringify({ version: v, at: Date.now() }));
  } catch {}
}

export default function App() {
  const [step, setStep] = useState<Step>("loading");
  const [lang, setLang] = useState<Lang>(loadLang());
  const t = useMemo(() => makeT(lang), [lang]);
  const [sel, setSel] = useState<Set<string>>(new Set(["home", "vet"]));
  const [entitlement, setEntitlement] = useState<Entitlement | null>(null);
  const [progress, setProgress] = useState({
    percent: 0,
    label: "",
    state: "downloading",
    speedMbps: 0,
    downloadedMb: 0,
    totalMb: 0,
  });
  const [installed, setInstalled] = useState<string[]>([]);
  const [shortcutDone, setShortcutDone] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launchErr, setLaunchErr] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMac, setIsMac] = useState(false); // = Docker-host (macOS veya Linux)
  const [hostOs, setHostOs] = useState<string>("windows");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [modal, setModal] = useState<null | {
    message: string;
    confirmText: string;
    cancelText?: string;
    danger?: boolean;
    onConfirm: () => void;
  }>(null);
  const [updateVer, setUpdateVer] = useState("");
  const [showUpdateSkip, setShowUpdateSkip] = useState(false);
  const skipUpdateRef = useRef(false);
  // Watchdog için güncel step (setState-yan-etkisiz, StrictMode-güvenli).
  const stepRef = useRef<Step>(step);
  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  const changeLang = (l: Lang) => {
    setLang(l);
    saveLang(l);
  };
  const openLink = (u: string) => void openUrl(u).catch(() => {}); // unhandled-rejection önle
  // Profil ad/slogan — seçili dile göre (config TR; i18n EN).
  const pName = (id: string) => PROFILE_I18N[id]?.[lang]?.name ?? PROFILES.find((p) => p.id === id)?.name ?? id;
  const pTag = (id: string) =>
    PROFILE_I18N[id]?.[lang]?.tagline ?? PROFILES.find((p) => p.id === id)?.tagline ?? "";
  const pModels = (id: string): readonly string[] =>
    PROFILE_I18N[id]?.[lang]?.models ?? PROFILES.find((p) => p.id === id)?.models ?? [];
  // Rust'ın gönderdiği (TR) ilerleme etiketini UI diline çevir (backend'e dil geçmemek için basit eşleme).
  const tLabel = (raw: string): string => {
    if (lang === "tr" || !raw) return raw;
    if (raw === "Sürüm bilgisi alınıyor…") return "Fetching version info…";
    if (raw === "Kuruluyor (yönetici izni gerekebilir)…") return "Installing (admin permission may be required)…";
    if (raw === "Tamamlandı") return "Completed";
    const m = raw.match(/^(.*) indiriliyor$/);
    if (m) return `Downloading ${m[1]}`;
    return raw;
  };

  const applyEntitlement = (e: Entitlement | null) => {
    setEntitlement(e);
    const al = allowedProfileIds(e);
    setSel(new Set(["home", "vet"].filter((id) => al.has(id))));
  };

  // Normal açılış (self-update yoksa): kuruluysa ready; değilse FREE_MODE→profiller / login.
  async function continueBoot() {
    try {
      const yes = await invoke<boolean>("is_installed").catch(() => false);
      if (yes) {
        const p = await invoke<string[]>("installed_profiles").catch(() => [] as string[]);
        setInstalled(p);
        if (p.length) setSel(new Set(p));
        setStep("ready");
        return;
      }
      if (FREE_MODE) {
        setStep("profiles");
        return;
      }
      const { data } = await supabase.auth.getSession();
      if (data.session) {
        applyEntitlement(await fetchEntitlement());
        setStep("profiles");
      } else {
        setStep("login");
      }
    } catch {
      // beklenmedik hata (supabase/ağ) → "loading"de takılma; kullanıcı elle ilerlesin
      setStep(FREE_MODE ? "profiles" : "login");
    }
  }

  useEffect(() => {
    (async () => {
      // macOS: Docker-yönlendiren MacLauncher.
      const os = await invoke<string>("get_os").catch(() => "windows");
      setHostOs(os);
      // macOS + Linux: native frozen backend çalışmaz → Docker-launcher (Mac dalıyla ortak).
      if (os === "macos" || os === "linux") {
        setIsMac(true);
        return;
      }
      // 1) ÖNCE kendi güncellemesi var mı? (internet varsa; hata → sessizce geç)
      try {
        // JS-tarafı zaman-sınırı: Rust connect/timeout'una ek emniyet — check asılırsa "loading"de
        // sonsuz "…" kalmasın (10sn sonra güncellemesiz normal açılışa geç).
        const up = await Promise.race([
          invoke<UpdateInfo | null>("check_client_update", {
            current: BRAND.version,
            url: CLIENT_UPDATE_URL,
          }),
          new Promise<null>((r) => setTimeout(() => r(null), 10000)),
        ]);
        // sürüm + sha256 + url dolu VE aynı sürüm son 4 saatte denenmemiş → güncelle.
        if (up && up.version && up.url && up.sha256 && !recentlyAttempted(up.version)) {
          markAttempt(up.version); // UAC reddi → tekrar-tekrar deneme döngüsünü kır
          setUpdateVer(up.version);
          setStep("updating");
          // İndirme uzun sürerse (~25sn) "Güncellemeyi atla" çıkışı göster → kullanıcı belirsiz
          // çubukta 10 dk kilitli kalmasın (skip → continueBoot; helper arka planda sürer).
          skipUpdateRef.current = false;
          setShowUpdateSkip(false);
          const skipTimer = window.setTimeout(() => {
            if (stepRef.current === "updating") setShowUpdateSkip(true);
          }, 25000);
          try {
            await invoke("run_client_update", { url: up.url, sha256: up.sha256 });
            if (skipUpdateRef.current) return; // kullanıcı atladı → poll kurma
            // Yardımcının GERÇEK durumunu izle (zaman-yarışı watchdog yerine): 'elevating' → bekle
            // (yavaş kurulum/UAC açık; erken un-stick YOK); 'declined'/'failed' → hemen normale dön;
            // 'done' → normale dön (installer client'ı kapatmış olmalı). Helper hiç yazmazsa 20sn,
            // sert tavan 5 dk. Böylece yavaş-ama-başarılı kurulum erken kesilmez.
            const startedAt = Date.now();
            const poll = window.setInterval(() => {
              if (stepRef.current !== "updating") {
                window.clearInterval(poll);
                return;
              }
              void invoke<string>("client_update_status")
                .catch(() => "")
                .then((st) => {
                  const elapsed = Date.now() - startedAt;
                  const settled = st === "declined" || st === "failed" || st === "done";
                  const helperSilent = st === "" && elapsed > 20000;
                  if (settled || helperSilent || elapsed > 300000) {
                    window.clearInterval(poll);
                    void continueBoot();
                  }
                });
            }, 2000);
            return;
          } catch {
            // güncelleme başlatılamadı (indirme/doğrulama hatası) → normal açılışa dön
          } finally {
            window.clearTimeout(skipTimer);
          }
        }
      } catch {
        // check başarısız (offline vb.) → normal açılış
      }
      await continueBoot();
    })();
  }, []);

  async function afterLogin() {
    try {
      applyEntitlement(await fetchEntitlement());
    } catch {
      applyEntitlement(null); // entitlement çekilemese de profillere geç (home-only), login'de takılma
    }
    setStep("profiles");
  }
  async function logout() {
    await supabase.auth.signOut();
    setEntitlement(null);
    setStep("login");
  }

  const allowed = FREE_MODE ? null : allowedProfileIds(entitlement);
  const chosen = PROFILES.filter((m) => sel.has(m.id));
  const gb = chosen.reduce((s, m) => s + m.sizeGB, 0) + CLIENT_BASE_MB / 1024;
  const addon = chosen.reduce((s, m) => s + m.addonMonthly, 0);

  const toggle = (id: string) => {
    if (allowed && !allowed.has(id)) return;
    setSel((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  async function install(forceFull = false) {
    if (sel.size === 0) return;
    const profiles = [...sel];
    setError(null);
    setProgress({ percent: 0, label: t("inst.starting"), state: "downloading", speedMbps: 0, downloadedMb: 0, totalMb: 0 });
    setStep("installing");
    let un: UnlistenFn = () => {};
    let listenOk = true;
    un = await listen<InstallProgress>("install://progress", (e) => {
      const p = e.payload;
      if (p.error) {
        un();
        setError(p.error);
        return;
      }
      setProgress({
        percent: p.percent,
        label: p.label,
        state: p.state,
        speedMbps: p.speedMbps,
        downloadedMb: p.downloadedMb,
        totalMb: p.totalMb,
      });
      if (p.done) {
        un();
        if (p.state === "cancelled") {
          setStep("profiles");
          return;
        }
        // 'installed'ı SENKRON ayarla → "ready"/Başlat asla boş profil-setiyle çizilmez
        // (installed_profiles IPC gidiş-dönüşünde Başlat'a basılırsa profilsiz URL olmasın).
        setInstalled(profiles);
        invoke<string[]>("installed_profiles")
          .then((actual) => {
            const eff = actual.length ? actual : profiles;
            setInstalled(eff);
            return invoke("create_shortcuts", { url: appUrlFor(eff) });
          })
          .then(() => setShortcutDone(true))
          .catch(() => {
            invoke("create_shortcuts", { url: appUrlFor(profiles) })
              .then(() => setShortcutDone(true))
              .catch(() => {});
          });
        setStep("ready");
      }
    }).catch((): UnlistenFn => {
      // listen kaydı başarısız (nadir; core:default izin verir) → boş 0%'da kilitlenme yerine hata
      listenOk = false;
      return () => {};
    });
    if (!listenOk) {
      setError(t("inst.listenErr"));
      return;
    }
    invoke("start_install", { profiles, manifest: MANIFEST_URL, forceFull }).catch((err) => {
      un();
      setError(String(err));
    });
  }

  const pause = () => invoke("pause_install").catch(() => {});
  const resume = () => invoke("resume_install").catch(() => {});
  const cancel = () => invoke("cancel_install").catch(() => {});

  const appUrlFor = (profs: string[]) =>
    profs.length ? `${APP_URL}?profiles=${encodeURIComponent(profs.join(","))}` : APP_URL;
  // "Başlat" → uygulamayı KENDİ native penceresinde açar (tarayıcı yok). Native pencere açılamazsa
  // (nadir) güvenli yedek: tarayıcıda aç → Başlat hiçbir zaman "hiçbir şey yapmaz" olmasın.
  // "Başlat": open_app backend hazır olana dek bekler (Rust tarafı). Hazır değilse Err("backend-not-ready")
  // → kullanıcıya "servis hazır değil" mesajı. Bekleme sırasında buton "Başlatılıyor…" + disabled.
  const launch = async () => {
    if (launching) return;
    setLaunchErr(false);
    setLaunching(true);
    try {
      await invoke("open_app", { url: appUrlFor(installed) });
    } catch {
      setLaunchErr(true);
    } finally {
      setLaunching(false);
    }
  };

  function uninstallApp() {
    setModal({
      message: t("ready.uninstallConfirm"),
      confirmText: t("ready.uninstall"),
      cancelText: t("common.cancel"),
      danger: true,
      onConfirm: async () => {
        setModal(null);
        setUninstalling(true);
        try {
          await invoke("uninstall_app");
          setInstalled([]);
          setStep("profiles");
        } catch (e) {
          setModal({
            message: t("ready.uninstallFail") + String(e),
            confirmText: t("common.ok"),
            onConfirm: () => setModal(null),
          });
        } finally {
          setUninstalling(false);
        }
      },
    });
  }

  return (
    <div className="bg-hero flex h-full flex-col">
      {/* Marka çubuğu */}
      <header className="flex items-center justify-between border-b border-border/70 bg-bg/60 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/25">
            <Logo className="h-5 w-5" />
          </span>
          <div className="leading-none">
            <div className="text-sm font-bold">{BRAND.name}</div>
            <div className="mt-0.5 text-[10px] text-muted">{BRAND.tagline}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          {/* Dil */}
          <div className="flex items-center overflow-hidden rounded-md border border-border-strong">
            {(["tr", "en"] as Lang[]).map((l) => (
              <button
                key={l}
                onClick={() => changeLang(l)}
                aria-pressed={lang === l}
                aria-label={l === "tr" ? "Türkçe" : "English"}
                className={`px-2 py-1 font-semibold uppercase transition-colors ${
                  lang === l ? "bg-primary/20 text-primary-strong" : "text-muted hover:text-fg"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
          <button
            onClick={() => openLink(LINKS.website)}
            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-muted transition-colors hover:bg-white/5 hover:text-fg"
          >
            <Globe className="h-3.5 w-3.5" /> {t("hdr.website")}
          </button>
          <button
            onClick={() => setAboutOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-muted transition-colors hover:bg-white/5 hover:text-fg"
          >
            <Info className="h-3.5 w-3.5" /> {t("hdr.about")}
          </button>
          <span className="mx-1 h-4 w-px bg-border" />
          <span className="inline-flex items-center gap-1.5 text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-success" /> v{BRAND.version}
          </span>
        </div>
      </header>

      {/* İçerik */}
      {/* justify-center: yatay ortala (orijinal — doğru çalışıyordu). items-safe-center: dikey ortala
          AMA içerik taşınca üstten kırpma yerine 'start'a düşer + kaydırılır (index.css'te tanımlı). */}
      <main className="flex flex-1 items-safe-center justify-center overflow-y-auto p-6">
        {isMac ? (
          <MacLauncher lang={lang} os={hostOs} />
        ) : (
          <>
            {step === "loading" && (
              <div className="flex flex-col items-center gap-4">
                <span className="grid h-16 w-16 animate-pulse place-items-center rounded-2xl bg-primary/15 text-primary ring-1 ring-primary/25">
                  <Logo className="h-9 w-9" />
                </span>
                <div className="text-sm text-muted">{t("boot.loading")}</div>
              </div>
            )}

            {step === "updating" && (
              <div className="flex max-w-md flex-col items-center gap-4 text-center">
                <span className="grid h-16 w-16 animate-pulse place-items-center rounded-2xl bg-primary/15 text-primary ring-1 ring-primary/25">
                  <Download className="h-8 w-8" />
                </span>
                <h1 className="text-2xl font-bold">
                  {t("upd.available", { v: updateVer })}
                </h1>
                <p className="text-sm text-muted">{t("upd.restartNote")}</p>
                <div className="mt-1 h-1.5 w-40 overflow-hidden rounded-full bg-panel">
                  <div className="h-full w-1/3 animate-pulse rounded-full bg-gradient-to-r from-primary-strong to-primary" />
                </div>
                {showUpdateSkip && (
                  <button
                    className="btn-ghost !text-muted mt-2"
                    onClick={() => {
                      skipUpdateRef.current = true;
                      setShowUpdateSkip(false);
                      void continueBoot();
                    }}
                  >
                    {t("upd.skip")}
                  </button>
                )}
              </div>
            )}

            {step === "login" && <Login onDone={afterLogin} lang={lang} />}

            {step === "profiles" && (
              <div className="w-full max-w-4xl">
                {/* Hero: tanıtım + telefon önizleme */}
                <div className="grid items-center gap-6 sm:grid-cols-[1fr_auto]">
                  <div>
                    <span className="chip">
                      <Sparkle className="h-3.5 w-3.5" /> {t("prof.badge")}
                    </span>
                    <h1 className="mt-4 text-2xl font-bold sm:text-3xl">{t("prof.title")}</h1>
                    <p className="mt-2 text-sm text-muted">{t("prof.sub")}</p>

                    {/* Tanıtım — özellik şeridi */}
                    <div className="mt-5 grid grid-cols-2 gap-2">
                      {FEATURES.map((f) => {
                        const Icon = FEATURE_ICONS[f.icon];
                        return (
                          <div
                            key={f.icon}
                            title={t(`feat.${f.icon}.d`)}
                            className="flex items-center gap-2 rounded-lg border border-border bg-white/[0.02] px-3 py-2"
                          >
                            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary/12 text-primary ring-1 ring-primary/20">
                              {Icon && <Icon className="h-4 w-4" />}
                            </span>
                            <span className="text-xs font-semibold leading-tight">{t(`feat.${f.icon}.t`)}</span>
                          </div>
                        );
                      })}
                    </div>

                    {!FREE_MODE && entitlement && (
                      <p className="mt-4 inline-flex items-center gap-1.5 text-xs text-muted">
                        <span className="text-fg/80">{entitlement.email}</span>
                        <span>· {t("prof.plan")} ·</span>
                        <button onClick={logout} className="inline-flex items-center gap-1 text-primary hover:underline">
                          <LogOut className="h-3.5 w-3.5" /> {t("prof.logout")}
                        </button>
                      </p>
                    )}
                  </div>

                  {/* Telefon çerçeveli app önizleme */}
                  <div className="hidden sm:block">
                    <div
                      style={{ width: 150 }}
                      className="mx-auto rounded-[1.5rem] border border-border-strong bg-black/40 p-1.5 shadow-2xl ring-1 ring-white/5"
                    >
                      <img
                        src={appPreview}
                        alt={t("prof.preview")}
                        style={{ height: 280, objectFit: "cover", objectPosition: "top" }}
                        className="block w-full rounded-[1.1rem]"
                      />
                    </div>
                    <div className="mt-2 text-center text-[11px] text-muted">{t("prof.preview")}</div>
                  </div>
                </div>

                {/* Profil kartları */}
                <div className="mt-6 grid gap-4 sm:grid-cols-3">
                  {PROFILES.map((m) => {
                    const on = sel.has(m.id);
                    const locked = !!allowed && !allowed.has(m.id);
                    const Icon = PROFILE_ICONS[m.id];
                    const ms = pModels(m.id);
                    return (
                      <button
                        key={m.id}
                        onClick={() => toggle(m.id)}
                        disabled={locked}
                        className={`card relative p-5 text-left transition-all ${
                          locked
                            ? "cursor-not-allowed opacity-45"
                            : on
                              ? "ring-2 ring-primary/60 glow-ring"
                              : "hover:border-border-strong"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/20">
                            {Icon && <Icon className="h-5 w-5" />}
                          </span>
                          {locked ? (
                            <span className="grid h-6 w-6 place-items-center rounded-md border border-border-strong text-muted">
                              <Lock className="h-3.5 w-3.5" />
                            </span>
                          ) : (
                            <span
                              className={`grid h-6 w-6 place-items-center rounded-md border transition-colors ${
                                on ? "border-primary bg-primary text-primary-fg" : "border-border-strong text-transparent"
                              }`}
                            >
                              <Check className="h-4 w-4" />
                            </span>
                          )}
                        </div>
                        <div className="mt-3 font-bold">{pName(m.id)}</div>
                        <p className="mt-1 text-xs leading-relaxed text-muted">{pTag(m.id)}</p>
                        <div className="mt-2.5 flex flex-wrap gap-1">
                          {ms.slice(0, 3).map((x) => (
                            <span
                              key={x}
                              className="rounded border border-border bg-white/[0.02] px-1.5 py-0.5 text-[10px] text-muted"
                            >
                              {x}
                            </span>
                          ))}
                          {ms.length > 3 && (
                            <span className="px-1 py-0.5 text-[10px] text-primary/80">+{ms.length - 3}</span>
                          )}
                        </div>
                        <div className="mt-2.5 flex items-center gap-2 text-xs">
                          <span className="font-semibold">≈ {m.sizeGB.toFixed(1)} GB</span>
                          <span className="text-muted">·</span>
                          {locked ? (
                            <span className="font-semibold text-warning">{t("prof.locked")}</span>
                          ) : FREE_MODE ? (
                            <span className="font-semibold text-success">{t("prof.free")}</span>
                          ) : m.included ? (
                            <span className="font-semibold text-success">{t("prof.included")}</span>
                          ) : (
                            <span className="font-semibold text-primary">+{tl(m.addonMonthly)}{t("prof.perMonth")}</span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Özet + kur */}
                <div className="card mt-5 flex flex-col items-center justify-between gap-4 p-5 sm:flex-row">
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
                    <span className="text-muted">
                      {t("prof.download")} <b className="text-fg">≈ {gb.toFixed(1)} GB</b>
                    </span>
                    {!FREE_MODE && (
                      <span className="text-muted">
                        {t("prof.extra")}{" "}
                        <b className={addon ? "text-primary" : "text-success"}>{addon ? `+${tl(addon)}` : t("prof.none")}</b>
                      </span>
                    )}
                  </div>
                  <button className="btn-primary" onClick={() => install()} disabled={sel.size === 0}>
                    <Download className="h-4 w-4" /> {t("prof.install")}
                  </button>
                </div>
              </div>
            )}

            {step === "installing" &&
              (error ? (
                <div className="w-full max-w-md text-center">
                  <span
                    className="grid mx-auto h-16 w-16 place-items-center rounded-2xl text-2xl font-bold ring-1 ring-white/10"
                    style={{ background: "oklch(70% 0.19 22 / 0.14)", color: "oklch(72% 0.19 22)" }}
                  >
                    !
                  </span>
                  <h1 className="mt-6 text-2xl font-bold">{t("inst.failTitle")}</h1>
                  <p className="mt-2 break-words text-sm text-muted">{error}</p>
                  <div className="mt-7 flex justify-center gap-3">
                    <button
                      className="btn-ghost"
                      onClick={() => {
                        setError(null);
                        setStep("profiles");
                      }}
                    >
                      {t("inst.back")}
                    </button>
                    <button className="btn-primary" onClick={() => install()}>
                      <Refresh className="h-4 w-4" /> {t("inst.retry")}
                    </button>
                  </div>
                </div>
              ) : (
                (() => {
                  const st = progress.state;
                  const paused = st === "paused";
                  const retrying = st === "retrying";
                  const installing = st === "installing";
                  const remainMb = Math.max(0, progress.totalMb - progress.downloadedMb);
                  const etaSec =
                    progress.speedMbps > 0.05 && !paused && !retrying ? remainMb / progress.speedMbps : 0;
                  const etaTxt =
                    etaSec > 0
                      ? etaSec >= 90
                        ? `~${Math.ceil(etaSec / 60)} ${t("inst.eta.min")}`
                        : `~${Math.ceil(etaSec)} ${t("inst.eta.sec")}`
                      : "";
                  const stateTxt = paused
                    ? t("inst.st.paused")
                    : retrying
                      ? t("inst.st.retry")
                      : installing
                        ? t("inst.st.installing")
                        : t("inst.st.downloading");
                  return (
                    <div className="w-full max-w-md text-center">
                      <span
                        className={`grid mx-auto h-16 w-16 place-items-center rounded-2xl ring-1 ${
                          paused ? "bg-muted/10 text-muted ring-white/10" : "bg-primary/12 text-primary ring-primary/25"
                        }`}
                      >
                        {paused ? <Pause className="h-8 w-8" /> : <Download className="h-8 w-8" />}
                      </span>
                      <h1 className="mt-6 text-2xl font-bold">
                        {installing ? t("inst.installing") : paused ? t("inst.paused") : t("inst.downloading")}
                      </h1>
                      <p className="mt-2 h-5 truncate px-2 text-sm text-muted">{tLabel(progress.label)}</p>

                      <div className="mt-6 h-2.5 w-full overflow-hidden rounded-full bg-panel">
                        <div
                          className={`h-full rounded-full transition-all duration-200 ${
                            paused
                              ? "bg-muted/50"
                              : retrying
                                ? "bg-amber-500/70"
                                : "bg-gradient-to-r from-primary-strong to-primary"
                          }`}
                          style={{ width: `${progress.percent}%` }}
                        />
                      </div>

                      <div className="mt-3 flex items-center justify-between text-xs">
                        <span className="font-semibold text-primary">
                          {lang === "tr" ? `%${progress.percent}` : `${progress.percent}%`}
                        </span>
                        <span className="text-muted">
                          {progress.totalMb > 0 ? `${fmtGb(progress.downloadedMb)} / ${fmtGb(progress.totalMb)} GB` : ""}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className={retrying ? "text-amber-500" : "text-muted"}>{stateTxt}</span>
                        <span className="text-muted">
                          {!paused && !retrying && !installing && progress.speedMbps > 0
                            ? `${progress.speedMbps.toFixed(1)} MB/s${etaTxt ? " · " + etaTxt : ""}`
                            : ""}
                        </span>
                      </div>

                      {!installing && (
                        <div className="mt-7 flex justify-center gap-3">
                          {paused ? (
                            <button className="btn-primary" onClick={resume}>
                              <Play className="h-4 w-4" /> {t("inst.resume")}
                            </button>
                          ) : (
                            <button className="btn-ghost" onClick={pause}>
                              <Pause className="h-4 w-4" /> {t("inst.pause")}
                            </button>
                          )}
                          <button className="btn-ghost !text-muted" onClick={cancel}>
                            <Close className="h-4 w-4" /> {t("inst.cancel")}
                          </button>
                        </div>
                      )}

                      <p className="mt-6 text-xs text-muted">
                        {installing ? t("inst.noteInstalling") : t("inst.noteDownloading")}
                      </p>
                    </div>
                  );
                })()
              ))}

            {step === "ready" && (
              <div className="w-full max-w-lg text-center">
                <span className="grid mx-auto h-16 w-16 place-items-center rounded-2xl bg-success/15 text-success ring-1 ring-success/25">
                  <Check className="h-8 w-8" />
                </span>
                <h1 className="mt-6 text-3xl font-bold">{t("ready.title")}</h1>
                <p className="mt-2 text-sm text-muted">{t("ready.sub")}</p>

                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {PROFILES.filter((m) => installed.includes(m.id)).map((m) => (
                    <span key={m.id} className="chip">
                      <Check className="h-3.5 w-3.5" /> {pName(m.id)}
                    </span>
                  ))}
                </div>

                <button
                  className="btn-primary mt-7 !px-8 !py-3.5 text-base disabled:opacity-70"
                  onClick={launch}
                  disabled={launching}
                >
                  <Play className="h-5 w-5" /> {launching ? t("ready.launching") : t("ready.launch")}
                </button>
                {launchErr && (
                  <p className="mt-3 text-sm text-amber-500">{t("ready.launchFailed")}</p>
                )}

                <div className="mt-5 flex flex-wrap items-center justify-center gap-4 text-xs text-muted">
                  {shortcutDone && (
                    <span className="inline-flex items-center gap-1.5 text-success">
                      <Check className="h-3.5 w-3.5" /> {t("ready.shortcut")}
                    </span>
                  )}
                  <button
                    className="inline-flex items-center gap-1.5 hover:text-fg"
                    onClick={async () => {
                      // Kurulu-açılışta entitlement çekilmez → değiştir'de (gating açıkken) ücretli
                      // profiller yanlış kilitli görünmesin diye burada çek.
                      if (!FREE_MODE && !entitlement)
                        applyEntitlement(await fetchEntitlement().catch(() => null));
                      setStep("profiles");
                    }}
                  >
                    <Refresh className="h-3.5 w-3.5" /> {t("ready.change")}
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 hover:text-fg"
                    onClick={() =>
                      setModal({
                        message: t("ready.repairConfirm"),
                        confirmText: t("ready.repair"),
                        cancelText: t("common.cancel"),
                        onConfirm: () => {
                          setModal(null);
                          install(true);
                        },
                      })
                    }
                  >
                    <Refresh className="h-3.5 w-3.5" /> {t("ready.repair")}
                  </button>
                  <button
                    className="inline-flex items-center gap-1.5 hover:text-danger disabled:opacity-60"
                    onClick={uninstallApp}
                    disabled={uninstalling}
                  >
                    <Close className="h-3.5 w-3.5" /> {uninstalling ? t("ready.uninstalling") : t("ready.uninstall")}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Alt bilgi */}
      <footer className="flex items-center justify-between border-t border-border/70 px-5 py-2.5 text-[11px] text-muted">
        <div className="flex items-center gap-2.5">
          <span>© {BRAND.company}</span>
          <span className="h-3 w-px bg-border" />
          <button
            onClick={() => openLink(LINKS.website)}
            className="inline-flex items-center gap-1 transition-colors hover:text-fg"
          >
            <Globe className="h-3 w-3" /> {t("hdr.website")}
          </button>
          <button onClick={() => openLink(LINKS.support)} className="transition-colors hover:text-fg">
            {t("about.support")}
          </button>
        </div>
        <span className="inline-flex items-center gap-1.5">
          {isMac ? (
            <>
              <Bolt className="h-3 w-3 text-primary" /> {hostOs === "linux" ? "Linux" : "macOS"} · Docker
            </>
          ) : step === "ready" ? (
            <>
              <Bolt className="h-3 w-3 text-primary" /> {BRAND.name} v{BRAND.version}
            </>
          ) : (
            <>
              {BRAND.name} <ArrowRight className="h-3 w-3" /> v{BRAND.version}
            </>
          )}
        </span>
      </footer>

      {aboutOpen && <About onClose={() => setAboutOpen(false)} lang={lang} />}
      {modal && (
        <ConfirmModal
          message={modal.message}
          confirmText={modal.confirmText}
          cancelText={modal.cancelText}
          danger={modal.danger}
          onConfirm={modal.onConfirm}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  );
}
