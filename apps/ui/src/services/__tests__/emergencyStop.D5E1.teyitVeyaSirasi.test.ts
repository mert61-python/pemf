// Author: mertaygn, cglrgrkn
/**
 * D5.E1 (İG-6.29 · K-3 · D5 3. dalga) — ACİL DURDUR teyidi ve kart reddi 1. VEYA 2. adımın backend yanıtıdır; yanıtların
 * GELİŞ SIRASI sonucu değiştirmez (GEÇ gelen yanıt erken teyidi / reddi EZMEZ, GEÇ gelen teyit / red de BEKLENİR).
 * ======================================================================================================================
 * ÖLÇÜLEN KÖR NOKTA (HEAD d38b0db5): `performEmergencyStop` 1. adım (köprü, ham `fetch`) ile 2. adımı (yetkili uç, `apiPost`)
 * AYNI ANDA gönderir (SGI-3.2); teyit iki yanıtın VEYA'sıdır (`if (… confirmed === true) teyitli = true`). Bu birikimi
 * `teyitli = r?.confirmed === true` (yedek yanıtı ÜZERİNE yazar) yapan mutant, yedek yanıtının köprüden ÖNCE çözüldüğü mevcut
 * testlerin HEPSİNDE (A63 / SGI32 / TD3 / emergencyStop.test — 37 dosya) YEŞİL kaldı: köprü STOP'u teyit ettiği hâlde yedek
 * yol GEÇ ve teyitsiz dönerse ekran "teyit edilemedi — fiziksel güç düğmesinden kapatın" der (yanlış alarm; D1.105'in alarm
 * körlüğü sınıfı). Bu kapı SIRAYI açıkça kurar (ertelenmiş yanıtlar) ve TAM matrisi ölçer:
 *   · teyit  : {köprü, yedek} teyit eder × {köprü, yedek} ÖNCE gelir → `{confirmed:true, kartReddetti:false}`
 *   · red    : {köprü, yedek} kartın reddini taşır (öteki red OLMAYAN partial) × iki sıra → `{confirmed:false, kartReddetti:true}`
 *   · teyit + red (öteki yol) × iki sıra → teyitli, `kartReddetti:false` (teyit varken KART_RED metni yok)
 *   · KARŞIT: iki yol da red olmayan partial × iki sıra → `{confirmed:false, kartReddetti:false}`
 * D5.E1 TUR 2 (çürütme p1 / p3, ikisi de 1. turda YAŞADI): `kartRed = r?.stmKartYaniti === "red"` (ikiz birikimci GEÇ yedekle
 * EZİLİR) → "red köprüde, köprü önce" kolu KIRMIZI; teyidi 2. adım BEKLENMEDEN okumak (`const _anlik = teyitli; await adim2`) →
 * "teyit yedekte, köprü önce" kolu KIRMIZI.
 *
 * Gövdeler backend'in GERÇEK yanıt biçimidir (K-3 sondası: D1105 aparatı + TestClient ile üretildi); biçimleri backend'de
 * şu pytest kapıları pinler: `test_D1105_teyit_ekseni_A63_STM_onayina_gore.py` (teyitli · ESP açık + yayın başarısız →
 * `stmStopped:true, confirmed:false` · porta yazılamadı → `stmStopped:false`) ve `test_TD3_estop_kartin_STOP_NACKi_teyit_DEGILDIR.py`
 * (kart yanıtsız → `stmKartYaniti:"yanitsiz"`, kart reddi → `"red"`).
 * Yedek gönderimler (A-63) her sırada aynı kalır (Ö.4-Y8) — bu dosya yalnız TEYİT / RED birikimini ölçer.
 * D5.E1 TUR 3 (çürütme 2 e1n1): köprü ARIZASI (2xx ama gövde JSON değil / okunurken iptal / JSON null · HTTP 500 · erişilemez) ×
 * yedek {3 partial, teyitli, kart reddi, erişilemez} × iki sıra → sonuç YALNIZ yedeğin gövdesinden (HTTP başarısı teyit sayılmaz);
 * simetriği: yedek arızası (erişilemez / `null`) × köprü {3 partial, teyitli, kart reddi} × iki sıra → sonuç köprünün gövdesinden.
 *
 * ⚠️ MUTASYON: 2. adımda `teyitli = r?.confirmed === true` → "teyit köprüde, köprü önce" KIRMIZI; 1. adımda `teyitli = d1?.confirmed
 * === true` → "teyit yedekte, yedek önce" KIRMIZI; `kartReddetti: kartRed` → "teyit + red" KIRMIZI; `kartRed = r?.… === "red"` →
 * "red köprüde, köprü önce" KIRMIZI; `kartRed = d1?.… === "red"` → "red yedekte, yedek önce" KIRMIZI; teyidi / reddi 2. adımdan
 * ÖNCE okumak → "… yedekte, köprü önce" KIRMIZI; okunamayan köprü gövdesinde `{ confirmed: response.ok }` → "köprü: 2xx, gövde …"
 * KIRMIZI (SAHTE teyit).
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "http://127.0.0.1:8000/api" },
}));

import { apiPost } from "@/services/apiClient";
import { performEmergencyStop } from "@/services/emergencyStop";

const mockApiPost = apiPost as jest.Mock;
const fetchMock = () => (global as unknown as { fetch: jest.Mock }).fetch;
const yollar = () => mockApiPost.mock.calls.map((c) => c[0]);
const YEDEK_YOLLAR = ["/hardware/emergency_stop", "/hardware/command", "/session/stop"];

// Backend'in GERÇEK E-stop gövdeleri (istemcinin okuduğu alanlar; K-3 sondası `_emergency_stop_all` çıktısı).
const TEYITLI = {
  status: "success", confirmed: true, stmStopped: true, stmKartYaniti: "kabul",
  mqttResults: [{ coilId: 8, mqtt: "devre_disi" }],
};
const PARTIAL: Record<string, Record<string, unknown>> = {
  esp_acik_mqtt_yok: {
    status: "partial", confirmed: false, stmStopped: true, stmKartYaniti: "kabul",
    mqttResults: [{ coilId: 8, mqtt: "mqtt_unavailable" }],
  },
  porta_yazilamadi: {
    status: "partial", confirmed: false, stmStopped: false, stmKartYaniti: null,
    mqttResults: [{ coilId: 8, mqtt: "devre_disi" }],
  },
  kart_yanitsiz: {
    status: "partial", confirmed: false, stmStopped: true, stmKartYaniti: "yanitsiz",
    mqttResults: [{ coilId: 8, mqtt: "devre_disi" }],
  },
};
const KART_RED = {
  status: "partial", confirmed: false, stmStopped: true, stmKartYaniti: "red",
  mqttResults: [{ coilId: 8, mqtt: "devre_disi" }],
};

type Yol = "kopru" | "yedek";
const SIRALAR: Yol[] = ["kopru", "yedek"];

/** Ertelenmiş yanıt: testin seçtiği anda çözülür (sırayı zamanlayıcıya bırakmaz). */
function ertele<T>() {
  let coz: (v: T) => void = () => undefined;
  const p = new Promise<T>((r) => { coz = r; });
  return { p, coz };
}
const bosalt = () => new Promise((r) => setTimeout(r, 0));

/** D5.E1 TUR 3: köprü yanıtı GÖVDESİZ / HATALI (gövde okunamaz, HTTP hata, erişilemez) — `yanit()` fetch'in çözdüğü değeri
 *  ya da (Error ise) fetch'in reddini üretir. */
class KopruArizasi {
  constructor(readonly ad: string, readonly yanit: () => unknown) {}
}
const kopruYaniti = (g: unknown) =>
  g instanceof KopruArizasi ? g.yanit() : { ok: true, status: 200, json: async () => g };
/** Ertelenmiş değer Error ise ret (erişilemeyen yol), değilse çözüm. */
const cozVeyaReddet = (p: Promise<unknown>) => p.then((r) => (r instanceof Error ? Promise.reject(r) : r));

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

/** Önce `ilk` adım çözülür, akış onu işler; SONRA öteki adım çözülür. */
async function sirayla(ilk: Yol, kopru: unknown, yedek: unknown) {
  const k = ertele<unknown>();
  const y = ertele<unknown>();
  fetchMock().mockImplementation(() => cozVeyaReddet(k.p));
  mockApiPost.mockImplementation((p: string) =>
    p === "/hardware/emergency_stop" ? cozVeyaReddet(y.p) : Promise.resolve({ status: "success" }));
  const sonuc = performEmergencyStop();
  await bosalt();
  if (ilk === "kopru") {
    k.coz(kopruYaniti(kopru));
    await bosalt();
    y.coz(yedek);
  } else {
    y.coz(yedek);
    await bosalt();
    k.coz(kopruYaniti(kopru));
  }
  return sonuc;
}

/** `veren` yol `ozel` gövdeyi, öteki yol `oteki` gövdeyi döndürür; `ilk` önce çözülür. */
const yollaGore = (ilk: Yol, veren: Yol, ozel: unknown, oteki: unknown) =>
  sirayla(ilk, veren === "kopru" ? ozel : oteki, veren === "yedek" ? ozel : oteki);

describe.each(Object.keys(PARTIAL))("D5.E1 (İG-6.29) VEYA sırası — gerçek partial gövde: %s", (ad) => {
  describe.each(SIRALAR)("teyit veren yol: %s", (veren) => {
    it.each(SIRALAR)("KRİTİK teyit: o yol TEYİTLİ, öteki partial; %s ÖNCE gelir → teyit KORUNUR, yedekler YİNE gider", async (ilk) => {
      await expect(yollaGore(ilk, veren, TEYITLI, PARTIAL[ad])).resolves.toEqual({ confirmed: true, kartReddetti: false });
      expect(yollar()).toEqual(YEDEK_YOLLAR);
    });
  });

  describe.each(SIRALAR)("kart reddi veren yol: %s", (veren) => {
    it.each(SIRALAR)("KRİTİK red: o yol KART REDDİ, öteki red OLMAYAN partial; %s ÖNCE gelir → kartReddetti KORUNUR", async (ilk) => {
      await expect(yollaGore(ilk, veren, KART_RED, PARTIAL[ad])).resolves.toEqual({ confirmed: false, kartReddetti: true });
    });
  });

  it.each(SIRALAR)("KARŞIT: iki yol da partial; %s ÖNCE gelir → teyit YOK, kart reddi YOK", async (ilk) => {
    await expect(sirayla(ilk, PARTIAL[ad], PARTIAL[ad])).resolves.toEqual({ confirmed: false, kartReddetti: false });
  });
});

describe.each(SIRALAR)("D5.E1 teyit + red — teyit veren yol: %s", (veren) => {
  it.each(SIRALAR)("KRİTİK: öteki yol KART REDDİ; %s ÖNCE gelir → teyitli ve kartReddetti FALSE (teyit varken red metni yok)", async (ilk) => {
    await expect(yollaGore(ilk, veren, TEYITLI, KART_RED)).resolves.toEqual({ confirmed: true, kartReddetti: false });
  });
});

// ── D5.E1 TUR 3 (çürütme 2 e1n1): TEYİT = backend'in 2xx GÖVDESİNDEKİ `confirmed:true`; HTTP durumu / gövdesizlik teyit DEĞİLDİR ──
// `response.json().catch(() => ({ confirmed: response.ok }))` (köprü 2xx ama gövde okunamazsa HTTP başarısı teyit sayılır) yukarıdaki
// matriste ve 6.29 kümesinde (38 dosya / 248 test) YEŞİLDİ: aparat köprü gövdesini HEP okunur veriyordu. Oysa tam bu yol gerçek: gövde
// okuması zaman aşımının İÇİNDE (2026-08-17) — abort'ta `json()` reddeder. Sonuç SAHTE TEYİT olurdu (ekran "durduruldu" der, ESP bobini
// çalışıyor olabilir — `emergencyStop.ts`'in kendi yorumundaki "en ağır hata sınıfı"). Köprü arızasında sonuç YALNIZ yedeğin gövdesinden.
const iptalHatasi = () => Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
const KOPRU_ARIZALARI = [
  new KopruArizasi("2xx, gövde JSON değil", () => ({
    ok: true, status: 200, json: () => Promise.reject(new SyntaxError("Unexpected token < in JSON at position 0")),
  })),
  new KopruArizasi("2xx, gövde okunurken iptal (zaman aşımı)", () => ({
    ok: true, status: 200, json: () => Promise.reject(iptalHatasi()),
  })),
  new KopruArizasi("2xx, gövde JSON null", () => ({ ok: true, status: 200, json: async () => null })),
  new KopruArizasi("HTTP 500, gövde teyit İDDİA etse de", () => ({ ok: false, status: 500, json: async () => TEYITLI })),
  new KopruArizasi("köprü erişilemez (ağ hatası)", () => new TypeError("Network request failed")),
];
const YEDEK_SONUCLARI: [string, unknown, { confirmed: boolean; kartReddetti: boolean }][] = [
  ...Object.keys(PARTIAL).map(
    (ad): [string, unknown, { confirmed: boolean; kartReddetti: boolean }] => [
      `partial (${ad})`, PARTIAL[ad], { confirmed: false, kartReddetti: false },
    ]),
  ["TEYİTLİ", TEYITLI, { confirmed: true, kartReddetti: false }],
  ["KART REDDİ", KART_RED, { confirmed: false, kartReddetti: true }],
  ["erişilemez", new Error("apiPost zaman aşımı"), { confirmed: false, kartReddetti: false }],
];

describe.each(KOPRU_ARIZALARI.map((a) => [a.ad, a] as const))("D5.E1 TUR 3 — köprü: %s", (_ad, ariza) => {
  describe.each(YEDEK_SONUCLARI)("yedek: %s", (_y, yedek, beklenen) => {
    it.each(SIRALAR)("KRİTİK: köprünün HTTP durumu teyit DEĞİL — sonuç yalnız yedeğin gövdesinden; %s ÖNCE gelir", async (ilk) => {
      await expect(sirayla(ilk, ariza, yedek)).resolves.toEqual(beklenen);
      expect(yollar()).toEqual(YEDEK_YOLLAR);
    });
  });
});

// Simetrik: YEDEK arızası (erişilemez / gövdesiz `null`) köprünün teyidini ya da kart reddini SİLMEZ, uydurmaz (TUR 3 kendi mutantı
// "yedek erişilemezse `kartRed = false`" bu kol olmadan YEŞİLDİ).
const KOPRU_SONUCLARI = YEDEK_SONUCLARI.filter(([ad]) => ad !== "erişilemez");
const YEDEK_ARIZALARI: [string, unknown][] = [
  ["erişilemez", new Error("apiPost zaman aşımı")],
  ["gövdesiz (null)", null],
];
describe.each(YEDEK_ARIZALARI)("D5.E1 TUR 3 — yedek: %s", (_y, yedekAriza) => {
  describe.each(KOPRU_SONUCLARI)("köprü: %s", (_k, kopru, beklenen) => {
    it.each(SIRALAR)("KRİTİK: yedek arızası köprünün sonucunu DEĞİŞTİRMEZ; %s ÖNCE gelir", async (ilk) => {
      await expect(sirayla(ilk, kopru, yedekAriza)).resolves.toEqual(beklenen);
      expect(yollar()).toEqual(YEDEK_YOLLAR);
    });
  });
});
