// Author: mertaygn, cglrgrkn
/**
 * D1.E01 · İG-6.3 · A-52 — EŞLEŞTİRME KODU REDDEDİLİNCE BAĞLANTI ÖNCEKİ CİHAZDA KALIR.
 *
 * Ölçülen zarar (ADAY-DOGRULAMA-D0, İG-6.3; iki GERÇEK backend + tünel benzetimi): telefon A cihazıyla
 * seans sürerken Ayarlar'dan B'nin kodu girildi. health + device_id geçti, kod takası 429 ile düştü;
 * ama `cihazaBaglan` oturum içi tabanı takastan ÖNCE B'ye çevirmişti ve geri ALMIYORDU. Sonra basılan
 * ACİL DURDUR'un 7 isteğinin 7'si B'ye gitti (uç auth-muaf olduğu için B'de YÜRÜTÜLDÜ), A'ya 0 istek
 * gitti, A'nın bobinleri sürmeye devam etti.
 *
 * Sahip kararı A-52: reddedilen eşleştirmede bağlantı ÖNCEKİ cihazda kalır; mesaj bunu söyler.
 * Y8: ACİL DURDUR kapılanmaz — DOĞRU cihaza gider. A-63 maddelerinden (teyit ölçütü) ÖNCE gelir:
 * aksi hâlde yanlış cihazda yürüyen E-stop "teyitli" görünürdü.
 *
 * ⚠️ Bu dosya GERÇEK pairing + config + discovery + emergencyStop + apiClient zincirini koşar. Sahte
 * olan YALNIZ bulut kayıt defteri (Supabase `resolve_device`) ve `fetch`. `updateServiceConfig`
 * SAHTE DEĞİL — `pairing.test.ts` onu sahteliyordu; kusur bu yüzden süitte görünmüyordu.
 */
const mockKodlaCoz = jest.fn();
jest.mock("@/services/deviceRegistry", () => ({
  uzakCihaziKodlaCoz: (...a: unknown[]) => mockKodlaCoz(...a),
  uzakCihaziKimlikleCoz: jest.fn(async () => ({ durum: "yok" })),
  getRemoteUrlForDevice: jest.fn(async () => null),
}));

import AsyncStorage from "@react-native-async-storage/async-storage";

import * as config from "@/services/config";
import { performEmergencyStop } from "@/services/emergencyStop";
import { cihazaBaglan, eslesmeMesaji } from "@/services/pairing";

const A_ADRES = "192.168.1.50"; // telefonun LAN'da çalıştığı cihaz
const A_TABAN = "http://192.168.1.50:8000";
const B_TABAN = "https://d0-b.trycloudflare.com"; // reddedilen kodun çözüldüğü tünel
const B_KIMLIK = "PEMF-B-0001";
const B_KOD = "B7K2QX";

type Yanit = { ok: boolean; status: number; json: () => Promise<unknown> };
const yanit = (status: number, govde: unknown): Yanit => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => govde,
});

let istekler: string[] = [];
let bSaglikli = true;
let takasDurumu = 429;
let takasBeklet = false;
let takasBekletici: ((y: Yanit) => void) | null = null;

function sahteFetch(url: unknown): Promise<Yanit> {
  const u = String(url);
  istekler.push(u);
  if (u === `${B_TABAN}/api/health`) {
    return Promise.resolve(
      bSaglikli ? yanit(200, { service: "PEMF-Vet", status: "online", deviceId: B_KIMLIK }) : yanit(503, {}),
    );
  }
  if (u === `${B_TABAN}/api/auth/exchange`) {
    if (takasBeklet) {
      return new Promise((coz) => {
        takasBekletici = coz;
      });
    }
    return Promise.resolve(takasDurumu === 200 ? yanit(200, { token: "B-TOKEN" }) : yanit(takasDurumu, { detail: "red" }));
  }
  // ACİL DURDUR: teyitsiz yanıt → istemcinin 2. ve 3. yedek adımları da koşar; HEPSİNİN hedefi ölçülür.
  if (u.endsWith("/hardware/emergency_stop")) return Promise.resolve(yanit(200, { status: "partial", confirmed: false }));
  if (u.endsWith("/session/stop") || u.endsWith("/hardware/command")) {
    return Promise.resolve(yanit(200, { status: "success" }));
  }
  return Promise.resolve(yanit(404, {}));
}

const DURDURMA_UCLARI = ["/hardware/emergency_stop", "/session/stop", "/hardware/command"];
const durdurmaIstekleri = (bas: number) =>
  istekler.slice(bas).filter((u) => DURDURMA_UCLARI.some((son) => u.endsWith(son)));
const hostu = (u: string) => u.replace(/^https?:\/\//i, "").split("/")[0];

beforeEach(async () => {
  await AsyncStorage.clear();
  istekler = [];
  bSaglikli = true;
  takasDurumu = 429;
  takasBeklet = false;
  takasBekletici = null;
  mockKodlaCoz.mockReset();
  mockKodlaCoz.mockResolvedValue({ durum: "bulundu", url: B_TABAN, device: { device_id: B_KIMLIK } });
  (global as { fetch: unknown }).fetch = jest.fn(sahteFetch);
  // Telefon A cihazıyla LAN'da çalışıyor; A'nın token'ı oturumda.
  expect(config.updateServiceConfig(A_ADRES)).toBe(true);
  config.serviceConfig.apiToken = "A-TOKEN";
});

describe("D1.E01 · A-52 — reddedilen eşleştirme bağlantıyı ÖNCEKİ cihazda bırakır", () => {
  it.each([429, 403, 404])(
    "KRİTİK: B'nin kodu %i ile reddedilince ACİL DURDUR'un TÜM istekleri A'ya gider, B'ye 0",
    async (red) => {
      takasDurumu = red;
      const s = await cihazaBaglan(B_KOD);
      expect(s.durum).toBe("kod_reddedildi");
      // Senaryo gerçekten kuruldu: B'nin health'i ve takası DENENDİ (B'ye hiç gidilmeden yeşil olmasın).
      expect(istekler).toContain(`${B_TABAN}/api/health`);
      expect(istekler).toContain(`${B_TABAN}/api/auth/exchange`);

      const bas = istekler.length;
      const sonuc = await performEmergencyStop();
      const durdurma = durdurmaIstekleri(bas);
      // Teyitsiz yanıt verildiği için birincil + iki yedek adımın HEPSİ gönderilmiş olmalı (Y8: azalmaz).
      expect(durdurma).toHaveLength(4);
      expect(durdurma.filter((u) => hostu(u) === hostu(B_TABAN))).toEqual([]);
      expect(durdurma.every((u) => u.startsWith(`${A_TABAN}/api/`))).toBe(true);
      expect(sonuc.confirmed).toBe(false);

      // Oturum içi bağlantının TAMAMI A'da (REST + köprü + WS + token).
      expect(config.serviceConfig.apiBaseUrl).toBe(`${A_TABAN}/api`);
      expect(config.serviceConfig.bridgeBaseUrl).toBe(`${A_TABAN}/api`);
      expect(config.serviceConfig.websocketUrl).toBe("ws://192.168.1.50:8000/ws");
      expect(config.serviceConfig.apiToken).toBe("A-TOKEN");
    },
  );

  it("KRİTİK: takas yanıtı BEKLENİRKEN basılan ACİL DURDUR da A'ya gider", async () => {
    // Eşleştirme henüz doğrulanmadı: operatörün durdurmak istediği cihaz hâlâ A'dır.
    takasBeklet = true;
    const baglanti = cihazaBaglan(B_KOD);
    for (let i = 0; i < 50 && !takasBekletici; i++) await new Promise((r) => setTimeout(r, 0));
    expect(takasBekletici).not.toBeNull(); // takas gerçekten askıda

    const bas = istekler.length;
    await performEmergencyStop();
    const durdurma = durdurmaIstekleri(bas);
    expect(durdurma).toHaveLength(4);
    expect(durdurma.filter((u) => hostu(u) === hostu(B_TABAN))).toEqual([]);

    (takasBekletici as unknown as (y: Yanit) => void)(yanit(429, { detail: "red" }));
    expect((await baglanti).durum).toBe("kod_reddedildi");
    expect(config.serviceConfig.apiBaseUrl).toBe(`${A_TABAN}/api`);
  });

  it("KRİTİK: ret mesajı bağlantının ÖNCEKİ cihazda kaldığını söyler", async () => {
    const m = eslesmeMesaji(await cihazaBaglan(B_KOD));
    expect(m).toMatch(/önceki cihazda kaldı/i);
    expect(m).toMatch(/kabul edilmedi/i);
  });

  it("KARŞIT: B kapalıysa (health düşer) takas denenmez, bağlantı A'da kalır", async () => {
    bSaglikli = false;
    expect((await cihazaBaglan(B_KOD)).durum).toBe("ulasilamiyor");
    expect(istekler).not.toContain(`${B_TABAN}/api/auth/exchange`);
    const bas = istekler.length;
    await performEmergencyStop();
    const durdurma = durdurmaIstekleri(bas);
    expect(durdurma).toHaveLength(4);
    expect(durdurma.every((u) => u.startsWith(`${A_TABAN}/api/`))).toBe(true);
  });

  it("POZİTİF: B'nin kodu KABUL edilirse bağlantı B'ye geçer ve ACİL DURDUR B'ye gider", async () => {
    // "Hiç geçme" biçimindeki bir mutantın bu düzeltme sanılmasını engeller.
    takasDurumu = 200;
    const s = await cihazaBaglan(B_KOD);
    expect(s).toMatchObject({ durum: "ok", url: B_TABAN, deviceId: B_KIMLIK });
    expect(config.serviceConfig.apiBaseUrl).toBe(`${B_TABAN}/api`);
    expect(config.serviceConfig.websocketUrl).toBe("wss://d0-b.trycloudflare.com/ws");
    expect(config.serviceConfig.apiToken).toBe("B-TOKEN");
    const bas = istekler.length;
    await performEmergencyStop();
    const durdurma = durdurmaIstekleri(bas);
    expect(durdurma).toHaveLength(4);
    expect(durdurma.every((u) => u.startsWith(`${B_TABAN}/api/`))).toBe(true);
  });
});
