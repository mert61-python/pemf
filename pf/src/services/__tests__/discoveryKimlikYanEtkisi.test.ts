// Author: mertaygn, cglrgrkn
/**
 * [5.9] checkHealth KİMLİK YAN-ETKİSİ (2. tur denetimi, sahip onayı 2026-08-20).
 *
 * `checkHealth` başarılı her yanıtta deviceId'yi DİSKE yazıyordu; `pairing.cihazaBaglan` onu
 * token takasından ÖNCE çağırdığı için takas DÜŞSE de kayıtlı kimlik B cihazına dönüyordu —
 * 1. turun F3 değişmezi ("token yoksa kalıcı yazım yok") device_id için deliniyordu. Birim
 * testleri checkHealth'i mock'ladığı için görünmüyordu; bu dosya checkHealth'in KENDİSİNİ
 * (fetch mock'uyla) koşturur.
 *
 * DÜZELTME: `checkHealth(addr, requireDeviceId, { kimligiKaydet: false })` — eşleştirme
 * ön-probu kimlik yazmaz; kalıcı yazım takas BAŞARILI olduktan sonra pairing'in kendi
 * `setStoredDeviceId` çağrısında. Varsayılan DEĞİŞMEZ (karşıt-kanıt): keşif merdiveni
 * basamakları kimliği yazmaya devam eder (kendi-kendini onarma davranışı).
 */
const mockSetDeviceId = jest.fn();
const mockSetApiToken = jest.fn();

jest.mock("@/services/config", () => ({
  updateServiceConfig: jest.fn(() => true),
  serviceConfig: { baseUrl: "" },
  // Promise dönmeli: üretim kodu `.catch()` zincirler — düz undefined dönüş TypeError'la
  // dış try'a düşüp checkHealth'i sahte-false yapar (ilk koşuda ölçüldü).
  setStoredDeviceId: (...a: unknown[]) => { mockSetDeviceId(...a); return Promise.resolve(); },
  getStoredDeviceId: jest.fn(async () => null),
  setStoredApiToken: (...a: unknown[]) => mockSetApiToken(...a),
}));
jest.mock("@/services/deviceRegistry", () => ({
  getRemoteUrlForDevice: jest.fn(async () => null),
}));
jest.mock("@/services/apiClient", () => ({
  isPrivateHost: jest.fn(() => false),
}));

import { checkHealth } from "@/services/discovery";

const ID_ = "140936350360443";

function saglikliBackendFetch() {
  // checkHealth iki fetch atar: /api/health (OK + kimlik) ve provisionToken'ın /api/auth/token'ı.
  // Token ucu BAŞARILI döndürülür (YEREL senaryo) — ön-prob yan-etkisizliği tam olarak bu
  // durumda sınanmalı: uzak 403 zaten no-op'tur, yerel başarıda token yazılırsa F3 deliğinin
  // TOKEN kardeşi doğar (adversaryal inceleme RISK'i). Sıra değil URL ile ayrıştır.
  return jest.fn(async (url: string) => {
    if (String(url).includes("/api/health")) {
      return { ok: true, json: async () => ({ service: "PEMF-Vet", deviceId: ID_ }) } as Response;
    }
    if (String(url).includes("/api/auth/token")) {
      return { ok: true, json: async () => ({ token: "B-CIHAZI-TOKENI" }) } as Response;
    }
    return { ok: false, json: async () => ({}) } as Response;
  });
}

beforeEach(() => {
  mockSetDeviceId.mockReset();
  mockSetApiToken.mockReset();
  (global as { fetch?: unknown }).fetch = saglikliBackendFetch();
});

it("KRİTİK [5.9]: kimligiKaydet:false ile ÖN-PROB kimlik YAZMAZ (F3: token yoksa kalıcı yazım yok)", async () => {
  const ok = await checkHealth("https://ornek.trycloudflare.com", ID_, { kimligiKaydet: false });
  expect(ok).toBe(true); // prob yine doğrular — yalnız YAN ETKİ kalkar
  expect(mockSetDeviceId).not.toHaveBeenCalled();
});

it("KRİTİK [17. parti]: ÖN-PROB api_token'ı da YAZMAZ (F3 deliğinin token kardeşi)", async () => {
  // Adversaryal inceleme RISK'i: bayrak yalnız kimliği bastırıyordu; registry günün birinde
  // LAN adresi döndürürse takas düşse bile saklı token B cihazınınkine dönerdi.
  await checkHealth("https://ornek.trycloudflare.com", ID_, { kimligiKaydet: false });
  expect(mockSetApiToken).not.toHaveBeenCalled();
});

it("KARŞIT-KANIT: varsayılan çağrı kimliği+token'ı yazmaya DEVAM eder (keşif merdiveni kendini onarır)", async () => {
  const ok = await checkHealth("https://ornek.trycloudflare.com");
  expect(ok).toBe(true);
  expect(mockSetDeviceId).toHaveBeenCalledWith(ID_);
  expect(mockSetApiToken).toHaveBeenCalledWith("B-CIHAZI-TOKENI"); // temassız-auth bozulmasın
});

it("KARŞIT-KANIT [17. parti]: MERDİVEN BİÇİMLİ çağrı (requireDeviceId İLE, bayraksız) da yazar", async () => {
  // Adversaryal inceleme: eski karşıt-kanıt merdivenin gerçek çağrı şeklini sınamıyordu —
  // koşul `!requireDeviceId`e mutasyonlansa merdivenin kendini-onarma yazımı sessizce ölürdü.
  const ok = await checkHealth("https://ornek.trycloudflare.com", ID_);
  expect(ok).toBe(true);
  expect(mockSetDeviceId).toHaveBeenCalledWith(ID_);
});

it("KARŞIT-KANIT: requireDeviceId uyuşmazlığında false döner ve kimlik yazılmaz (yanlış-cihaz koruması aynen)", async () => {
  const ok = await checkHealth("https://ornek.trycloudflare.com", "BASKA-CIHAZ", { kimligiKaydet: false });
  expect(ok).toBe(false);
  expect(mockSetDeviceId).not.toHaveBeenCalled();
});
