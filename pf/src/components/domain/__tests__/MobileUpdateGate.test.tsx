// Author: mertaygn, cglrgrkn
/**
 * MOBİL AÇILIŞ KAPISI (2026-08-16 sahip isteği: "önce güncelleme kontrolü, sonra açılış ve
 * kullanım"). Masaüstündeki "Başlat" kapısının mobil karşılığı.
 *
 * Kilitlenen davranışlar — iki grup, ZIT yönde:
 *
 * A) KAPI GERÇEKTEN KAPANIR
 *    - kontrol sürerken uygulama ÇİZİLMEZ (asıl istek),
 *    - güncelleme varsa uygulama yerine güncelleme ekranı gelir.
 *
 * B) 🔴 KAPI ASLA KALICI KİLİTLENMEZ — hepsi ayrı ayrı sınanır. Biri düşerse tıbbi bir cihazın
 *    uzaktan kumandası açılmaz hale gelir; bu, düzeltilen arızadan çok daha kötüdür:
 *    - güncelleme yok → açılır,      - ağ/manifest hatası → açılır,
 *    - Android DIŞI → hiç kapanmaz,  - zaman aşımı → açılır,
 *    - "Atla" → açılır,              - "Şimdilik devam et" → açılır (indirme sürerken de).
 *
 * 🔴 Ayrıca: GEÇ GELEN SONUÇ EKRANI GERİ ALMAZ. Masaüstünde düzeltilen asıl arıza buydu —
 * kullanıcı tam dokunacakken ekranın altından kayması.
 */
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  createDownloadResumable: jest.fn(),
  getInfoAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));

// ⚠️ `guncellemeyiAtla`/`atlandiMi` GERÇEK bırakılır: kapı→bant susturması gerçekten sınansın
// (mock'lasaydık "çağrıldı mı" testi olurdu, "işe yarıyor mu" testi değil).
jest.mock("@/services/mobileUpdate", () => {
  const gercek = jest.requireActual("@/services/mobileUpdate");
  return {
    ...gercek,
    guncellemeVarMi: jest.fn(),
    apkIndir: jest.fn(),
    kurulumuBaslat: jest.fn(),
  };
});

import { render, act, fireEvent, waitFor } from "@testing-library/react-native";
import { Platform, Text } from "react-native";

import {
  MobileUpdateGate,
  ATLA_GORUNME_MS,
  KONTROL_ZAMAN_ASIMI_MS,
} from "@/components/domain/MobileUpdateGate";
import {
  apkIndir,
  atlandiMi,
  guncellemeVarMi,
  kurulumuBaslat,
  kurulumErtelendiMi,
  _atlamayiSifirla,
  _indirmeyiSifirla,
  _kurulumErtelemesiniSifirla,
  type MobilSurum,
} from "@/services/mobileUpdate";

const mockVarMi = guncellemeVarMi as jest.Mock;
const mockIndir = apkIndir as jest.Mock;
const mockKur = kurulumuBaslat as jest.Mock;

const SURUM: MobilSurum = {
  version: "2.4.0",
  versionCode: 30,
  url: "https://github.com/o/r/releases/download/t/PEMF_Vet_Mobil.apk",
  sha256: "a".repeat(64),
  size: 128_000_000,
  notes: "Bağlanma sorunları giderildi.",
};

const UYGULAMA = "UYGULAMA-ICERIGI";
const ciz = () =>
  render(
    <MobileUpdateGate>
      <Text>{UYGULAMA}</Text>
    </MobileUpdateGate>,
  );

/** Kontrol sonucunu bekleyen mikro-görevleri boşalt (sahte zamanlayıcılarla birlikte). */
const bekle = async () => { await act(async () => { await Promise.resolve(); }); };
/** Zamanı ilerlet (sahte zamanlayıcı). */
const ilerlet = async (ms: number) => { await act(async () => { jest.advanceTimersByTime(ms); }); };

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  _atlamayiSifirla();
  _indirmeyiSifirla();
  _kurulumErtelemesiniSifirla();
  (Platform as { OS: string }).OS = "android";
  mockVarMi.mockResolvedValue({ varMi: false, sebep: "guncel" });
  mockIndir.mockResolvedValue({ ok: true, dosyaUri: "file:///cache/x.apk" });
  mockKur.mockResolvedValue("acildi");
});

afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────────────────
// A) KAPI GERÇEKTEN KAPANIR — asıl istek
// ─────────────────────────────────────────────────────────────────────────────

it("🔴 ASIL İSTEK: kontrol BİTMEDEN uygulama ÇİZİLMEZ", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {})); // kontrol sürüyor
  const { queryByText, getByTestId } = ciz();
  await bekle();
  expect(queryByText(UYGULAMA)).toBeNull();
  expect(getByTestId("mobil-acilis-kapisi")).toBeTruthy();
});

it("kontrol sürerken kullanıcıya NE BEKLEDİĞİ yazılır", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { getByText } = ciz();
  await bekle();
  expect(getByText(/Güncelleme kontrol ediliyor/)).toBeTruthy();
});

it("güncelleme VARSA uygulama yerine güncelleme ekranı gelir", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { queryByText, getByText } = ciz();
  await bekle();
  expect(queryByText(UYGULAMA)).toBeNull();
  expect(getByText(/Yeni sürüm hazır: 2\.4\.0/)).toBeTruthy();
  expect(getByText(/Bağlanma sorunları giderildi/)).toBeTruthy(); // notlar kullanıcıya gösterilir
});

// ─────────────────────────────────────────────────────────────────────────────
// B) 🔴 KAPI ASLA KALICI KİLİTLENMEZ
// ─────────────────────────────────────────────────────────────────────────────

it("güncelleme YOKSA kapı AÇILIR", async () => {
  const { getByText } = ciz();
  await bekle();
  expect(getByText(UYGULAMA)).toBeTruthy();
});

it("🔴 KİLİTLENME: ağ/manifest hatasında kapı AÇILIR (internetsiz klinik)", async () => {
  mockVarMi.mockResolvedValue({ varMi: false, sebep: "manifest" });
  const { getByText } = ciz();
  await bekle();
  expect(getByText(UYGULAMA)).toBeTruthy();
});

it("🔴 KİLİTLENME: Android DIŞI platformda kapı HİÇ kapanmaz (web/iOS)", async () => {
  (Platform as { OS: string }).OS = "web";
  mockVarMi.mockReturnValue(new Promise(() => {})); // çözülmese bile
  const { getByText, queryByTestId } = ciz();
  expect(getByText(UYGULAMA)).toBeTruthy(); // İLK boyamada — tek kare bile bekletme yok
  expect(queryByTestId("mobil-acilis-kapisi")).toBeNull();
  // ⚠️ Etki kapısı da sınanır: web'de manifest HİÇ yoklanmamalı. (Mutasyon turu bunu ortaya
  // çıkardı: yalnız "ekranda ne var" bakan bir test, kapı kaldırılınca da yeşil kalıyordu.)
  await act(async () => {});
  expect(mockVarMi).not.toHaveBeenCalled();
});

it("🔴 KİLİTLENME: kontrol ASILIRSA zaman aşımı kapıyı AÇAR", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { queryByText } = ciz();
  await bekle();
  expect(queryByText(UYGULAMA)).toBeNull();
  await ilerlet(KONTROL_ZAMAN_ASIMI_MS);
  expect(queryByText(UYGULAMA)).toBeTruthy();
});

it("🔴 KİLİTLENME: 'Atla' kapıyı AÇAR", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { queryByText, getByTestId } = ciz();
  await bekle();
  await ilerlet(ATLA_GORUNME_MS);
  await act(async () => { fireEvent.press(getByTestId("kapi-atla")); });
  expect(queryByText(UYGULAMA)).toBeTruthy();
});

it("🔴 KİLİTLENME: güncelleme ekranında 'Şimdilik devam et' kapıyı AÇAR", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { queryByText, getByTestId } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(queryByText(UYGULAMA)).toBeTruthy();
});

it("🔴 KİLİTLENME: indirme DÜŞSE bile kullanıcı içeri girebilir", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockResolvedValue({ ok: false, hata: "indirme" });
  const { getByTestId, getByText, queryByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/Güncelleme indirilemedi/)).toBeTruthy());
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(queryByText(UYGULAMA)).toBeTruthy();
});

// ─────────────────────────────────────────────────────────────────────────────
// 🔴 GEÇ GELEN SONUÇ EKRANI GERİ ALMAZ (masaüstünde düzeltilen ASIL arıza)
// ─────────────────────────────────────────────────────────────────────────────

it("🔴 zaman aşımıyla açıldıktan SONRA gelen güncelleme ekranı GERİ ALMAZ", async () => {
  let cozumle: (v: unknown) => void = () => {};
  mockVarMi.mockReturnValue(new Promise((r) => { cozumle = r; }));
  const { queryByText } = ciz();
  await bekle();
  await ilerlet(KONTROL_ZAMAN_ASIMI_MS);
  expect(queryByText(UYGULAMA)).toBeTruthy();

  await act(async () => { cozumle({ varMi: true, surum: SURUM }); await Promise.resolve(); });
  expect(queryByText(UYGULAMA)).toBeTruthy();          // uygulama HÂLÂ ekranda
  expect(queryByText(/Yeni sürüm hazır/)).toBeNull();  // ekran ELİNDEN ALINMADI
});

it("🔴 'Atla'dan SONRA gelen güncelleme de ekranı GERİ ALMAZ", async () => {
  let cozumle: (v: unknown) => void = () => {};
  mockVarMi.mockReturnValue(new Promise((r) => { cozumle = r; }));
  const { queryByText, getByTestId } = ciz();
  await bekle();
  await ilerlet(ATLA_GORUNME_MS);
  await act(async () => { fireEvent.press(getByTestId("kapi-atla")); });

  await act(async () => { cozumle({ varMi: true, surum: SURUM }); await Promise.resolve(); });
  expect(queryByText(UYGULAMA)).toBeTruthy();
  expect(queryByText(/Yeni sürüm hazır/)).toBeNull();
});

// ─────────────────────────────────────────────────────────────────────────────
// "Atla" görünme zamanlaması — hasta güvenliği kaçış yolu
// ─────────────────────────────────────────────────────────────────────────────

it("'Atla' HEMEN görünmez (normal kontrolde kimse görmesin)", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { queryByTestId } = ciz();
  await bekle();
  expect(queryByTestId("kapi-atla")).toBeNull();
  await ilerlet(ATLA_GORUNME_MS - 100);
  expect(queryByTestId("kapi-atla")).toBeNull();
});

it("'Atla' zaman aşımından ÖNCE görünür — yoksa kaçış yolu olmazdı", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { getByTestId } = ciz();
  await bekle();
  await ilerlet(ATLA_GORUNME_MS);
  expect(getByTestId("kapi-atla")).toBeTruthy();
  expect(ATLA_GORUNME_MS).toBeLessThan(KONTROL_ZAMAN_ASIMI_MS);
});

// ─────────────────────────────────────────────────────────────────────────────
// İndirme / kurulum akışı
// ─────────────────────────────────────────────────────────────────────────────

it("'Güncelle ve kur' indirir ve kurulumu AÇAR", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { getByTestId } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(mockKur).toHaveBeenCalledWith("file:///cache/x.apk"));
  expect(mockIndir).toHaveBeenCalledWith(SURUM, expect.any(Function));
});

it("indirme yüzdesi kullanıcıya YAZILIR", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockImplementation(async (_s: MobilSurum, cb: (o: number) => void) => {
    cb(0.42);
    return new Promise(() => {}); // indirme sürüyor
  });
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/İndiriliyor… %42/)).toBeTruthy());
});

it("eksik inen paket için AYRI ve eylem söyleyen mesaj çıkar", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockResolvedValue({ ok: false, hata: "boyut" });
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/İndirme eksik kaldı/)).toBeTruthy());
});

it("kurulum açılamazsa 'bilinmeyen kaynak' izni SÖYLENİR", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockKur.mockResolvedValue("hata");
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/bilinmeyen kaynak/)).toBeTruthy());
});

it("⚠️ İNDİRME SÜRERKEN DE 'Şimdilik devam et' durur (128 MB beklenmez)", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockImplementation(async (_s: MobilSurum, cb: (o: number) => void) => {
    cb(0.1);
    return new Promise(() => {});
  });
  const { getByTestId, queryByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(queryByText(/İndiriliyor…/)).toBeTruthy());
  expect(getByTestId("kapi-devam")).toBeTruthy();
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(queryByText(UYGULAMA)).toBeTruthy();
});

// ─────────────────────────────────────────────────────────────────────────────
// Erteleme kaydı — kapı ile uygulama içi bandın konuşması
// ─────────────────────────────────────────────────────────────────────────────

it("'Şimdilik devam et' sürümü ERTELENMİŞ işaretler (bant hemen aynı şeyi dayatmasın)", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { getByTestId } = ciz();
  await bekle();
  expect(atlandiMi(SURUM.versionCode)).toBe(false);
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(atlandiMi(SURUM.versionCode)).toBe(true);
  expect(atlandiMi(SURUM.versionCode + 1)).toBe(false); // yalnız O sürüm ertelenir
  // [5.7a] hiç indirme başlamadıysa kurulum-ertelemesi de İŞARETLENMEZ (uçuşta iş yok)
  expect(kurulumErtelendiMi(SURUM.versionCode)).toBe(false);
});

it("⚠️ indirme BAŞLADIYSA erteleme İŞARETLENMEZ — bant kaldığı yerden sürdürsün", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockImplementation(async (_s: MobilSurum, cb: (o: number) => void) => {
    cb(0.3);
    return new Promise(() => {});
  });
  const { getByTestId, queryByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(queryByText(/İndiriliyor…/)).toBeTruthy());
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(atlandiMi(SURUM.versionCode)).toBe(false);
});

it("KRİTİK [5.7a]: indirme SÜRERKEN 'Şimdilik devam et' KURULUM-ERTELEMESİ işaretler — uçuştaki iş yükleyiciyi sormadan açamaz", async () => {
  // Ölçülen kusur: kapı kapanıyor, kullanıcı uygulamada; indirme bitince uçuştaki guncelle()
  // Android yükleyicisini o anki işin ÜSTÜNE açıyordu (seans kapısı ayrı katman; seanssız
  // kullanım korumasızdı). Bayrağı kancanın kurulum-öncesi kapısı okur.
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockImplementation(async (_s: MobilSurum, cb: (o: number) => void) => {
    cb(0.3);
    return new Promise(() => {});
  });
  const { getByTestId, queryByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(queryByText(/İndiriliyor…/)).toBeTruthy());
  expect(kurulumErtelendiMi(SURUM.versionCode)).toBe(false);
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(kurulumErtelendiMi(SURUM.versionCode)).toBe(true);
});

it("KRİTİK [5.7c]: paket TAM İNDİKTEN sonra 'Şimdilik devam et' bandı SUSTURMAZ (hazır paket banttan sunulmaya devam eder)", async () => {
  // Ölçülen kusur: oran===null yordamı "hiç başlamadı" ile "tamamlandı"yı ayırt edemiyordu —
  // tam inmiş (ör. yükleyicisi açılıp vazgeçilmiş) paketten sonra erteleme bandı da susturuyor,
  // hazır paketi tek dokunuşla kurma yolunu soğuk açılışa erteliyordu.
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/onayını bekleyin/)).toBeTruthy()); // indirme bitti, yükleyici açıldı
  await act(async () => { fireEvent.press(getByTestId("kapi-devam")); });
  expect(atlandiMi(SURUM.versionCode)).toBe(false);           // bant SUSTURULMADI
  expect(kurulumErtelendiMi(SURUM.versionCode)).toBe(true);   // ama oto-açılış kesildi
});

it("kontrol aşamasında 'Atla' HİÇBİR sürümü ertelemiş saymaz", async () => {
  mockVarMi.mockReturnValue(new Promise(() => {}));
  const { getByTestId } = ciz();
  await bekle();
  await ilerlet(ATLA_GORUNME_MS);
  await act(async () => { fireEvent.press(getByTestId("kapi-atla")); });
  expect(atlandiMi(SURUM.versionCode)).toBe(false);
});

// ─────────────────────────────────────────────────────────────────────────────
// 🔴 SAHA BİLDİRİMİ 2026-08-17 — kurulum akışının kullanıcıya söyledikleri
// ─────────────────────────────────────────────────────────────────────────────

it("🔴 kurulum açılınca kullanıcı NE OLDUĞUNU görür (sessiz kalmaz)", async () => {
  // Eskiden başarıda hiçbir şey yazılmıyordu: paylaşım sayfası kapanınca ekran hiç değişmemiş
  // gibi duruyordu ve kullanıcı işlemin olup olmadığını bilmiyordu.
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/onayını bekleyin/)).toBeTruthy());
});

it("🔴 kurulum açıldıktan sonra düğme TEKRAR AÇMA işlevine döner", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  const { getByTestId, getByText } = ciz();
  await bekle();
  expect(getByText("Güncelle ve kur")).toBeTruthy();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText("Kurulumu tekrar aç")).toBeTruthy());
});

it("🔴 'bilinmeyen kaynak' izni yoksa NE YAPILACAĞI yazılır", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockKur.mockResolvedValue("izin_gerekli");
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/izin verip tekrar deneyin/)).toBeTruthy());
});

it("paylaşım yedeğine düşülürse kullanıcı SEBEBİNİ öğrenir", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockKur.mockResolvedValue("paylasim");
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  await waitFor(() => expect(getByText(/elle kurabilirsiniz/)).toBeTruthy());
});

it("indirme ilerlemesi MB olarak da yazılır (mobil kota görünsün)", async () => {
  mockVarMi.mockResolvedValue({ varMi: true, surum: SURUM });
  mockIndir.mockImplementation(async (_s: MobilSurum, cb: (o: number) => void) => {
    cb(0.5);
    return new Promise(() => {});
  });
  const { getByTestId, getByText } = ciz();
  await bekle();
  await act(async () => { fireEvent.press(getByTestId("kapi-guncelle")); });
  // 128.000.000 B * 0,5 = 64 MB / 128 MB
  await waitFor(() => expect(getByText(/%50 · 64 MB \/ 128 MB/)).toBeTruthy());
});

/**
 * [S5 adım 8 / kapsam-1] KAPI KAYDIRILABİLİR
 * ------------------------------------------
 * ÖLÇÜLEN DURUM: kök `View` sabit `flex:1 + justifyContent:center` idi. Yatay telefonda
 * (yükseklik 360-430) logo + marka + güncelleme kartı toplamı ekranı aşınca "Şimdilik devam et"
 * ve "Atla" düğmeleri görünür alanın ALTINDA kalıyordu — dosyanın kendi ilkesi olan
 * "kapı ASLA kalıcı kilitlenmez" görsel olarak kırılıyordu (mantık doğru, erişim yok).
 *
 * ⚠️ MUTASYON: kök tekrar View yapılırsa bu test KIRILIR.
 */
it("KRİTİK: kök kaydırılabilir — kısa ekranda çıkış düğmelerine ulaşılır", () => {
  const u = render(<MobileUpdateGate><Text>uygulama</Text></MobileUpdateGate>);
  const kok = u.getByTestId("mobil-acilis-kapisi");
  expect(kok.type).toBe("RCTScrollView");
  u.unmount();
});
