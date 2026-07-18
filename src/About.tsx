import { useEffect } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { BRAND, LINKS, FEATURES } from "./config";
import { Logo, Close, Globe, Download, Mail, ExternalLink, Cpu, Database, ShieldCheck, Cloud, FEATURE_ICONS } from "./Icons";
import { makeT, type Lang } from "./lib/i18n";

/** Hakkında modalı — ürün tanıtımı + özellikler + nasıl çalışır + sistem gereksinimleri + bağlantılar. */
export default function About({ onClose, lang }: { onClose: () => void; lang: Lang }) {
  const t = makeT(lang);
  // Escape ile kapan (klavye erişilebilirliği).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const steps = [
    { t: t("how.s1.t"), d: t("how.s1.d") },
    { t: t("how.s2.t"), d: t("how.s2.d") },
    { t: t("how.s3.t"), d: t("how.s3.d") },
  ];
  const reqs = [
    { Icon: Cpu, txt: t("sys.os") },
    { Icon: Database, txt: t("sys.ram") },
    { Icon: ShieldCheck, txt: t("sys.disk") },
    { Icon: Cloud, txt: t("sys.net") },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: "oklch(8% 0.03 264 / 0.68)", backdropFilter: "blur(6px)" }}
      onClick={onClose}
    >
      <div
        className="card glow-ring relative flex max-h-full w-full max-w-xl flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Üst şerit */}
        <div className="relative shrink-0 border-b border-border/70 p-6">
          <div className="flex items-center gap-3">
            <span className="grid h-12 w-12 place-items-center rounded-xl bg-primary/15 text-primary ring-1 ring-primary/25">
              <Logo className="h-7 w-7" />
            </span>
            <div>
              <div className="text-lg font-bold">{BRAND.name}</div>
              <div className="text-xs text-muted">{BRAND.tagline}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-lg text-muted transition-colors hover:bg-white/5 hover:text-fg"
            aria-label={t("about.close")}
          >
            <Close className="h-4 w-4" />
          </button>
        </div>

        <div className="overflow-y-auto p-6">
          <p className="text-sm leading-relaxed text-muted">{t("about.about")}</p>

          {/* Özellikler */}
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {FEATURES.map((f) => {
              const Icon = FEATURE_ICONS[f.icon];
              return (
                <div key={f.icon} className="flex gap-3 rounded-lg border border-border bg-white/[0.02] p-3">
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary ring-1 ring-primary/20">
                    {Icon && <Icon className="h-4 w-4" />}
                  </span>
                  <div>
                    <div className="text-sm font-semibold">{t(`feat.${f.icon}.t`)}</div>
                    <div className="text-xs leading-snug text-muted">{t(`feat.${f.icon}.d`)}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Nasıl çalışır (3 adım) */}
          <div className="mt-6">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">{t("how.title")}</div>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {steps.map((s, i) => (
                <div key={i} className="rounded-lg border border-border bg-white/[0.02] p-3">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-primary/15 text-sm font-bold text-primary-strong ring-1 ring-primary/25">
                    {i + 1}
                  </span>
                  <div className="mt-2 text-sm font-semibold">{s.t}</div>
                  <div className="mt-0.5 text-xs leading-snug text-muted">{s.d}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Sistem gereksinimleri */}
          <div className="mt-6">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">{t("sys.title")}</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {reqs.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/[0.03] text-muted">
                    <r.Icon className="h-3.5 w-3.5" />
                  </span>
                  <span className="text-fg/90">{r.txt}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bağlantılar */}
          <div className="mt-6 flex flex-wrap gap-2">
            <button className="btn-ghost !py-2 text-sm" onClick={() => openUrl(LINKS.website)}>
              <Globe className="h-4 w-4" /> {t("about.website")} <ExternalLink className="h-3.5 w-3.5 opacity-60" />
            </button>
            <button className="btn-ghost !py-2 text-sm" onClick={() => openUrl(LINKS.download)}>
              <Download className="h-4 w-4" /> {t("about.downloads")}
            </button>
            <button className="btn-ghost !py-2 text-sm" onClick={() => openUrl(LINKS.support)}>
              <Mail className="h-4 w-4" /> {t("about.support")}
            </button>
          </div>

          <div className="mt-5 flex items-center justify-between border-t border-border/70 pt-4 text-xs text-muted">
            <span>
              {t("about.version")} {BRAND.version}
            </span>
            <span>© {BRAND.company}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
