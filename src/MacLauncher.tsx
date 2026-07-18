import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { MAC } from "./config";
import { Check, Download, Play, Refresh, ArrowRight, Sparkle, Close } from "./Icons";
import { makeT, type Lang } from "./lib/i18n";

type Docker = "checking" | "not_installed" | "not_running" | "running";

/** macOS/Linux dalı — PEMF, Windows kurulumu yerine DOCKER ile koşar. Docker çalışınca
 *  "Başlat" imajları ghcr'den çeker (ilk sefer birkaç GB) → compose up → tarayıcı. */
export default function MacLauncher({ lang, os }: { lang: Lang; os?: string }) {
  const t = makeT(lang);
  const platform = os === "linux" ? "Linux" : "macOS";
  const [docker, setDocker] = useState<Docker>("checking");
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    setDocker("checking");
    const d = (await invoke<string>("mac_docker_status").catch(() => "not_installed")) as Docker;
    setDocker(d);
    setRunning(await invoke<boolean>("mac_running").catch(() => false)); // gerçek compose durumu (pencere yeniden açılınca da doğru)
  }
  useEffect(() => {
    refresh();
  }, []);

  const dockerOk = docker === "running";

  async function start() {
    setBusy(true);
    setMsg(t("mac.starting"));
    try {
      await invoke("mac_start");
      setRunning(true);
      setMsg(t("mac.runningMsg"));
    } catch (e) {
      setMsg(t("mac.startErr") + String(e));
    } finally {
      setBusy(false);
    }
  }
  async function stop() {
    setBusy(true);
    try {
      await invoke("mac_stop");
      setRunning(false);
      setMsg(t("mac.stopped"));
    } catch (e) {
      setMsg(t("mac.stopErr") + String(e));
    } finally {
      setBusy(false);
    }
  }

  const Dot = ({ ok }: { ok: boolean }) => (
    <span
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ring-1 ${
        ok ? "bg-success/15 text-success ring-success/25" : "bg-primary/12 text-primary ring-primary/20"
      }`}
    >
      {ok ? <Check className="h-4 w-4" /> : <span className="h-2 w-2 rounded-full bg-current" />}
    </span>
  );

  return (
    <div className="w-full max-w-xl">
      <div className="text-center">
        <span className="chip">
          <Sparkle className="h-3.5 w-3.5" /> {platform} · Docker
        </span>
        <h1 className="mt-4 text-2xl font-bold sm:text-3xl">{t("mac.title")}</h1>
        <p className="mt-2 text-sm text-muted">{t("mac.sub")}</p>
      </div>

      <div className="mt-7 flex flex-col gap-3">
        {/* Docker Desktop durumu — tek ön koşul (imajlar ghcr'den iner) */}
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <Dot ok={dockerOk} />
            <div className="min-w-0 flex-1">
              <div className="font-bold">Docker Desktop</div>
              <p className="mt-0.5 text-xs text-muted">
                {docker === "checking"
                  ? t("mac.checking")
                  : docker === "not_installed"
                    ? t("mac.notInstalled")
                    : docker === "not_running"
                      ? t("mac.notRunning")
                      : t("mac.running")}
              </p>
            </div>
            {docker === "not_installed" && (
              <button className="btn-ghost shrink-0 text-sm" onClick={() => openUrl(MAC.dockerUrl)}>
                <Download className="h-4 w-4" /> {t("mac.download")}
              </button>
            )}
            {docker === "not_running" && (
              <button className="btn-ghost shrink-0 text-sm" onClick={() => invoke("mac_open_docker").catch(() => {})}>
                {t("mac.open")}
              </button>
            )}
          </div>
        </div>

        {/* İlk-başlatma bilgi notu (ghcr indirme + GPU) */}
        <p className="px-1 text-center text-xs text-muted">{t("mac.pullNote")}</p>
      </div>

      {/* Başlat / Durdur */}
      <div className="card mt-4 flex flex-col items-center gap-3 p-5">
        {msg && <p className="break-words text-center text-xs text-muted">{msg}</p>}
        {!running ? (
          <button className="btn-primary !px-8 !py-3 text-base" onClick={start} disabled={!dockerOk || busy}>
            <Play className="h-5 w-5" /> {busy ? t("mac.startingBtn") : t("mac.startBtn")}
          </button>
        ) : (
          <div className="flex gap-3">
            <button className="btn-primary" onClick={() => openUrl("http://localhost:8080")}>
              <ArrowRight className="h-4 w-4" /> {t("mac.openBrowser")}
            </button>
            <button className="btn-ghost" onClick={stop} disabled={busy}>
              <Close className="h-4 w-4" /> {t("mac.stop")}
            </button>
          </div>
        )}
        <button
          className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg"
          onClick={refresh}
        >
          <Refresh className="h-3.5 w-3.5" /> {t("mac.refresh")}
        </button>
      </div>
    </div>
  );
}
