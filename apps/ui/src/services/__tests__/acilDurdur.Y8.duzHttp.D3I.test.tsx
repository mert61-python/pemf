// Author: mertaygn, cglrgrkn
/**
 * D3I-A1.3 — Ö.4-Y8: ACİL DURDUR ve STOP "hiçbir … düz-HTTP … kapısına bağlanmaz; gönderim yalnız ARTAR (yedekler azaltılamaz)".
 * HEAD: `performEmergencyStop`'un 1. adımı ham `fetch` (kapısız) ama 2. E-stop, `stop_all_coils` ve `/session/stop` yedekleri
 * `apiClient.apiPost`'un ilk satırındaki `isCleartextAllowed(serviceConfig.apiBaseUrl)` kapısında düşer → genel `http://` tabanında
 * 4 istek yerine 1; seans "Durdur"u (`useSessionControl.stopSession`) HİÇ gitmez (ekran "sunucuya ulaşılamadı" der — denenmedi bile).
 * D3.39 Y8 kapısı (`duzHttpKapisi.D3_39.test.ts`) yalnız "en az bir E-stop isteği" ölçtüğü için kördü.
 * ÇAĞRI YERLERİ GERÇEK: kayan ACİL DURDUR (`GlobalEmergencyStop` — kabuk, Giriş Y23, Karşılama A-58, hesap menüsü), Kontrol /
 * Ana Ekran ACİL DURDUR'u (`useSessionControl.emergencyStop`), çıkış / profil değişimi (`useTeardownGuard`, A-59), Durdur
 * (`useSessionControl.stopSession`). GERÇEK: config / apiClient / duzHttpKapisi / emergencyStop. Sahte EN ALT katta: `global.fetch`;
 * yalnız ekran kabuğu (canlı veri bağlamı, onay penceresi, tost, güvenli alan) sahte.
 * Ayrıca: `durdurma: true` bayrağı YALNIZ durdurma çağrılarında (AST) — E-stop dışı çağrıya sızamaz; genel http'ye giden yedekler
 * 1. adımdan FAZLA başlık taşımaz (Supabase Bearer / operatör jetonu güvenli taban kapısında kalır).
 */
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/hesapGecisi", () => ({ onaySonrasiEngel: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
const mockCanli = {
  snapshot: {
    stm: "online",
    coils: [1, 2, 3].map((id) => ({ id, connected: true, running: id === 1 })),
    activeTreatment: { isActive: true, mode: "Manuel" },
  },
  donanimBelirsiz: false,
};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => mockCanli }));
jest.mock("@/services/apiClient", () => ({
  ...jest.requireActual("@/services/apiClient"),
  platformConfirm: jest.fn(async () => true),
  platformAlert: jest.fn(),
}));

import React from "react";
import { act, fireEvent, render, renderHook } from "@testing-library/react-native";
import { updateServiceConfig, serviceConfig } from "../config";
import { setAuthBearer, setOperatorToken } from "../apiClient";
import { performEmergencyStop } from "../emergencyStop";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { useSessionControl } from "@/hooks/useSessionControl";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";

type Cagri = { yol: string; basliklar: string[] };
let cagrilar: Cagri[] = [];
const DURDURMA = /\/hardware\/emergency_stop|\/hardware\/command|\/session\/stop|\/coil\//;
const ESTOP_DORTLU = ["/api/hardware/command", "/api/hardware/emergency_stop", "/api/hardware/emergency_stop", "/api/session/stop"];

beforeEach(() => {
  cagrilar = [];
  (global as { fetch: unknown }).fetch = jest.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
    const yol = String(url).replace(/^https?:\/\/[^/]+/, "");
    if (DURDURMA.test(yol)) cagrilar.push({ yol, basliklar: Object.keys(init?.headers ?? {}).sort() });
    const g = { confirmed: true, status: "success" };
    return { ok: true, status: 200, json: async () => g, text: async () => JSON.stringify(g) };
  });
  serviceConfig.apiToken = "cihaz-anahtari";
  jest.spyOn(console, "error").mockImplementation(() => {});
  jest.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => {
  setAuthBearer(null);
  setOperatorToken(null);
  jest.restoreAllMocks();
});

const yollar = () => cagrilar.map((c) => c.yol).sort();
const TABANLAR: [string, string][] = [
  ["LAN", "http://192.168.1.5:8000"],
  ["https tünel", "https://abc-def.trycloudflare.com"],
  ["GENEL http", "http://203.0.113.5:8000"],
];

describe.each(TABANLAR)("%s tabanında ACİL DURDUR 4 istek (2× E-stop + stop_all_coils + seans durdurma)", (_ad, taban) => {
  beforeEach(() => expect(updateServiceConfig(taban)).toBe(true));

  it("KRİTİK Y8: kayan ACİL DURDUR (GlobalEmergencyStop)", async () => {
    const u = render(<GlobalEmergencyStop />);
    await act(async () => {
      fireEvent.press(u.getByText(/ACİL DURDUR/));
    });
    await act(async () => {});
    expect(yollar()).toEqual(ESTOP_DORTLU);
    u.unmount();
  });

  it("KRİTİK Y8: Kontrol / Ana Ekran ACİL DURDUR (useSessionControl.emergencyStop)", async () => {
    const { result, unmount } = renderHook(() => useSessionControl());
    await act(async () => {
      await result.current.emergencyStop();
    });
    expect(yollar()).toEqual(ESTOP_DORTLU);
    unmount();
  });

  it("KRİTİK Y8: çıkış / profil değişimi söküm kapısı (useTeardownGuard, A-59)", async () => {
    const { result, unmount } = renderHook(() => useTeardownGuard());
    await act(async () => {
      expect(await result.current("Çıkış yapmak")).toBe(true);
    });
    expect(yollar()).toEqual(ESTOP_DORTLU);
    unmount();
  });

  it("KRİTİK Y8: seans Durdur (useSessionControl.stopSession) GÖNDERİLİR", async () => {
    const { result, unmount } = renderHook(() => useSessionControl());
    await act(async () => {
      await result.current.stopSession();
    });
    expect(yollar()).toEqual(["/api/session/stop"]);
    unmount();
  });
});

it("KRİTİK: genel http'de yedekler 1. adımdan FAZLA başlık taşımaz — Supabase Bearer / operatör jetonu GİTMEZ", async () => {
  updateServiceConfig("http://203.0.113.5:8000");
  setAuthBearer("supabase-jwt");
  setOperatorToken("operator-jetonu");
  await performEmergencyStop();
  expect(yollar()).toEqual(ESTOP_DORTLU);
  const ilk = cagrilar[0].basliklar; // 1. adım (ham fetch) — Y8 gereği zaten gidiyordu
  for (const c of cagrilar) {
    expect(c.basliklar).not.toContain("Authorization");
    expect(c.basliklar).not.toContain("X-PEMF-Operator");
    expect(c.basliklar.filter((b) => !ilk.includes(b) && b !== "Accept")).toEqual([]);
  }
});

// ── `durdurma: true` YALNIZ durdurma çağrılarında (kaynak AST) ──────────────────────────────────────────────────────────────────
const KOK = path.resolve(__dirname, "..", "..");
const IZINLI_DURDURMA: Record<string, string[]> = {
  "services/emergencyStop.ts": ["/hardware/command", "/hardware/emergency_stop", "/session/stop"],
  "hooks/useSessionControl.ts": ["/session/stop"],
  "screens/ControlScreen.tsx": ["/coil/${coilId}/control", "/coil/batch"],
  // D3I çapraz (C2): bobin paneli Durdur + D1.82 STOP yinelemesi · AI Pro açık Durdur + panel kapanış durdurması
  "components/domain/CoilParameterPanel.tsx": ["/coil/${coilId}/control", "/coil/${coilId}/control"],
  "components/domain/AiProPanel.tsx": ["/ai/pro/stop", "/ai/pro/stop"],
};
function durdurmaCagrilari(): Record<string, string[]> {
  const sonuc: Record<string, string[]> = {};
  const gez = (dizin: string) => {
    for (const ad of fs.readdirSync(dizin)) {
      const tam = path.join(dizin, ad);
      if (fs.statSync(tam).isDirectory()) {
        if (ad !== "__tests__" && ad !== "node_modules") gez(tam);
        continue;
      }
      if (!/\.(ts|tsx)$/.test(ad)) continue;
      const kaynak = fs.readFileSync(tam, "utf8");
      if (!kaynak.includes("durdurma")) continue;
      const sf = ts.createSourceFile(tam, kaynak, ts.ScriptTarget.Latest, true);
      const rel = path.relative(KOK, tam).split(path.sep).join("/");
      const ziyaret = (n: ts.Node) => {
        if (ts.isPropertyAssignment(n) && n.name.getText(sf) === "durdurma") {
          // `durdurma: true` YALNIZ apiPost'un 4. argümanında, sabit yol + (bobin yollarında) start:false gövdeyle
          const nesne = n.parent;
          const cagri = nesne?.parent;
          let yol = "<apiPost DIŞI>";
          if (cagri && ts.isCallExpression(cagri) && cagri.expression.getText(sf) === "apiPost" && cagri.arguments[3] === nesne) {
            yol = cagri.arguments[0].getText(sf).replace(/^["`]|["`]$/g, "");
            const govde = cagri.arguments[1].getText(sf);
            if (yol.startsWith("/coil") && !/start:\s*false/.test(govde)) yol += " <start:false DEĞİL>";
            if (yol === "/hardware/command" && !/stop_all_coils/.test(govde)) yol += " <stop_all_coils DEĞİL>";
          }
          (sonuc[rel] ??= []).push(`${yol}${n.initializer.getText(sf) === "true" ? "" : " <true DEĞİL>"}`);
        }
        ts.forEachChild(n, ziyaret);
      };
      ziyaret(sf);
    }
  };
  gez(KOK);
  for (const k of Object.keys(sonuc)) sonuc[k].sort();
  return sonuc;
}

it("KRİTİK: `durdurma` bayrağı YALNIZ durdurma çağrılarında — E-stop / STOP dışına sızmaz (apiClient tanımı hariç)", () => {
  const bulunan = durdurmaCagrilari();
  delete bulunan["services/apiClient.ts"]; // tanım + kapı ifadesi (`opts?.durdurma`) — çağrı değil
  expect(bulunan).toEqual(IZINLI_DURDURMA);
});

it("KARŞIT: bayraksız apiPost genel http'de YİNE engellenir (kapı daralmadı)", async () => {
  updateServiceConfig("http://203.0.113.5:8000");
  const { apiPost } = jest.requireActual("@/services/apiClient");
  expect(await apiPost("/hardware/command", { command: "stop_all_coils", params: {} }, "fb", { silent: true })).toBe("fb");
  expect(await apiPost("/session/start", {}, "fb", { silent: true })).toBe("fb");
  expect(cagrilar).toEqual([]);
});
