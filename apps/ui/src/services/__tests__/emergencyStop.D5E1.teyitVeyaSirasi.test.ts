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
 *
 * ⚠️ MUTASYON: 2. adımda `teyitli = r?.confirmed === true` → "teyit köprüde, köprü önce" KIRMIZI; 1. adımda `teyitli = d1?.confirmed
 * === true` → "teyit yedekte, yedek önce" KIRMIZI; `kartReddetti: kartRed` → "teyit + red" KIRMIZI; `kartRed = r?.… === "red"` →
 * "red köprüde, köprü önce" KIRMIZI; `kartRed = d1?.… === "red"` → "red yedekte, yedek önce" KIRMIZI; teyidi / reddi 2. adımdan
 * ÖNCE okumak → "… yedekte, köprü önce" KIRMIZI.
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
const kopruYaniti = (g: unknown) => ({ ok: true, status: 200, json: async () => g });

beforeEach(() => {
  mockApiPost.mockReset();
  (global as { fetch: unknown }).fetch = jest.fn();
});

/** Önce `ilk` adım çözülür, akış onu işler; SONRA öteki adım çözülür. */
async function sirayla(ilk: Yol, kopru: unknown, yedek: unknown) {
  const k = ertele<unknown>();
  const y = ertele<unknown>();
  fetchMock().mockImplementation(() => k.p);
  mockApiPost.mockImplementation((p: string) =>
    p === "/hardware/emergency_stop" ? y.p : Promise.resolve({ status: "success" }));
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
