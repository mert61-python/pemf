// Author: mertaygn, cglrgrkn
/**
 * TEK GÜNCELLEME KANALI — mobil taraf (2026-08-09 denetimi, Tier 3).
 *
 * ARIZA: banner'da "Cihaz yazılımı güncellemesi var — Dokun ve Güncelle" satırı vardı ve
 * backend'in `/api/update/apply` ucunu çağırıyordu. O uç bir Inno installer'ı `/VERYSILENT`
 * çalıştırıyordu; oysa cihazın kurulumunu artık PEMF Vet Client (launcher) yönetir. Sonuç:
 * launcher'ın yönettiği kurulumun YANINA ikinci bir backend + ikinci veri kökü → seanslar iki
 * ayrı hasta veritabanına bölünür ve HER İKİSİ de eksiksiz görünür (split-brain).
 *
 * Bu testler mobil arayüzün cihaz yazılımına BİR DAHA dokunmamasını kilitler. APK (sideload)
 * bildirimi kalır — o ayrı ve meşru bir kanaldır.
 */
// `mock` ön eki zorunlu: jest.mock fabrikası kapsam-dışı değişkene erişemez.
const mockApiGet = jest.fn(async () => ({}));
const mockApiPost = jest.fn(async () => ({ ok: true }));
jest.mock("@/services/apiClient", () => ({ apiGet: mockApiGet, apiPost: mockApiPost }));

import { render, waitFor } from "@testing-library/react-native";
import { Platform } from "react-native";
import { UpdateBanner } from "@/components/ui/UpdateBanner";

const apiGet = mockApiGet;
const apiPost = mockApiPost;

// APK bildirimi YALNIZ Android'de anlamlıdır (iOS'ta sideload yok) — testte o dalı sür.
Object.defineProperty(Platform, "OS", { get: () => "android", configurable: true });

const gercekFetch = global.fetch;

function manifestVer(govde: unknown) {
  global.fetch = jest.fn(async () => ({ ok: true, json: async () => govde })) as unknown as typeof fetch;
}

beforeEach(() => {
  apiGet.mockClear();
  apiPost.mockClear();
  manifestVer({ version: "0.0.0", apkUrl: "" });
});

afterAll(() => { global.fetch = gercekFetch; });

it("KRİTİK: banner backend güncelleme uçlarına HİÇ dokunmaz", async () => {
  render(<UpdateBanner />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  // `mock.calls` tipi argümansız fn için boş tuple → index'lemek TS hatası; düzleştirip bak.
  const cagrilar = [...apiGet.mock.calls, ...apiPost.mock.calls].flat().map(String);
  expect(cagrilar.filter((u) => u.includes("/update/"))).toEqual([]);
});

it("KRİTİK: 'cihaz yazılımı güncelle' düğmesi ARTIK YOK", async () => {
  // Manifest yeni APK bildirse bile cihaz-yazılımı satırı çizilmemeli.
  manifestVer({
    version: "99.0.0",
    apkUrl: "https://github.com/mert61-python/pemf-update/releases/download/x/app.apk",
  });
  const u = render(<UpdateBanner />);
  await waitFor(() => expect(u.queryByText(/Uygulama güncellemesi var/)).toBeTruthy());
  expect(u.queryByText(/Cihaz yazılımı/i)).toBeNull();
});

it("APK bildirimi (meşru kanal) çalışmaya devam eder", async () => {
  manifestVer({
    version: "99.0.0",
    apkUrl: "https://github.com/mert61-python/pemf-update/releases/download/x/app.apk",
  });
  const u = render(<UpdateBanner />);
  await waitFor(() => expect(u.getByText(/Uygulama güncellemesi var \(v99\.0\.0\)/)).toBeTruthy());
});

it("güncelleme yoksa hiçbir şey çizilmez", async () => {
  const u = render(<UpdateBanner />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  expect(u.toJSON()).toBeNull();
});

it("services/updates backend güncelleme fonksiyonu İHRAÇ ETMEZ", () => {
  // Düğme kaldırılıp fonksiyon bırakılırsa, bir sonraki ekran onu yeniden çağırabilir.
  const m = require("@/services/updates");
  expect(m.applyBackendUpdate).toBeUndefined();
  expect(m.checkBackendUpdate).toBeUndefined();
});
