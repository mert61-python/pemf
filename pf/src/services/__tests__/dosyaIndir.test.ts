// Author: mertaygn
/**
 * "İNDİR" DÜĞMELERİ SESSİZCE ÖLÜYORDU — 2026-09-11 saha arızasının kapısı.
 *
 * Sahip: "excel csv indir, tümü pdf indir butonları çalışmıyor seans geçmişi tabında."
 *
 * KÖK NEDEN: arayüz Tauri v2 **WebView2** penceresinde koşuyor. İndirme
 * `fetch → blob → <a download>.click()` ile yapılıyordu; bu WebView2'de ancak uygulama
 * bir indirme işleyicisi kaydederse çalışır — `launcher/app/src/main.rs` hiçbir
 * `on_download`/dialog/fs eklentisi KAYDETMİYOR. Tıklama hiçbir şey yapmıyordu.
 *
 * ⚠️ ASIL ZARARI BÜYÜTEN ŞEY: kod `a.click()`ten sonra HİÇBİR geri bildirim vermiyordu.
 * "Çalıştı" ile "öldü" operatör için AYNI görünüyordu; arıza bu yüzden aylarca
 * fark edilmeden durabilirdi.
 *
 * Bu dosya üç dalı da ölçer ve her dalda "sessiz dönüş" olmadığını kilitler.
 */
const mockFetch = jest.fn();
const mockDownloadAsync = jest.fn();
const mockShareAsync = jest.fn();
const mockIsSharingAvailable = jest.fn();
const mockDeleteAsync = jest.fn();

let mockPlatformOS = "web";
jest.mock("react-native", () => ({ Platform: { get OS() { return mockPlatformOS; } } }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/tmp/",
  downloadAsync: (...a: unknown[]) => mockDownloadAsync(...(a as [])),
  deleteAsync: (...a: unknown[]) => mockDeleteAsync(...(a as [])),
}));
jest.mock("expo-sharing", () => ({
  isAvailableAsync: (...a: unknown[]) => mockIsSharingAvailable(...(a as [])),
  shareAsync: (...a: unknown[]) => mockShareAsync(...(a as [])),
}));

const mockConfig = { apiBaseUrl: "http://localhost:8000/api", apiToken: "" };
// ⚠️ GETTER ŞART, düz `{ serviceConfig: mockConfig }` DEĞİL: `jest.mock` çağrıları
// babel tarafından dosyanın EN ÜSTÜNE taşınır ve fabrika, `const mockConfig` daha
// başlatılmadan koşabilir → `serviceConfig` sonsuza dek `undefined` kalır (ölçüldü:
// "Cannot read properties of undefined (reading 'apiToken')"). Getter okumayı
// ERİŞİM ANINA erteler.
jest.mock("@/services/config", () => ({ get serviceConfig() { return mockConfig; } }));

import { downloadFileWithAuth, backendBuMakinede } from "@/services/dosyaIndir";

/** Toplanan toast'lar — "sessiz dönüş" kapılarının ölçüm yüzeyi. */
let toastlar: [string, string | undefined][] = [];
const toast = (m: string, t?: "success" | "error" | "info") => { toastlar.push([m, t]); };

/** `<a download>` tıklaması gerçekten yapıldı mı (tarayıcı dalı). */
let tiklamaSayisi = 0;

beforeEach(() => {
  toastlar = [];
  tiklamaSayisi = 0;
  mockPlatformOS = "web";
  mockConfig.apiBaseUrl = "http://localhost:8000/api";
  mockFetch.mockReset();
  mockDownloadAsync.mockReset();
  mockShareAsync.mockReset();
  mockIsSharingAvailable.mockReset();
  mockDeleteAsync.mockReset().mockResolvedValue(undefined);

  (globalThis as Record<string, unknown>).fetch = mockFetch;
  (globalThis as Record<string, unknown>).URL = Object.assign(
    function (u: string, b?: string) { return new (jest.requireActual("url").URL)(u, b); },
    { createObjectURL: () => "blob:sahte", revokeObjectURL: () => {} },
  );
  const a = { href: "", download: "", click: () => { tiklamaSayisi += 1; }, remove: () => {} };
  (globalThis as Record<string, unknown>).document = {
    createElement: () => a,
    body: { appendChild: () => {} },
  };
});

const yanit = (o: Partial<{ ok: boolean; status: number; tur: string; json: unknown; metin: string }>) => ({
  ok: o.ok ?? true,
  status: o.status ?? 200,
  headers: { get: () => o.tur ?? "application/pdf" },
  json: async () => o.json ?? {},
  text: async () => o.metin ?? "",
  blob: async () => ({ size: 10 }),
});

// ============================================================================
// 1. YEREL BACKEND — dosyayı sunucu diske yazar
// ============================================================================

test("KRITIK: backend BU MAKINEDEYSE kaydet=1 gonderilir ve YOL bildirilir", async () => {
  // ⚠️ ASIL KAPI. MUTASYON: `backendBuMakinede()` dalını sil → KIRMIZI
  // (WebView2'de `<a download>` ölü olduğu için saha arızası geri gelir).
  mockFetch.mockResolvedValue(yanit({ tur: "application/json", json: { status: "success", yol: "C:/m/Desktop/x.csv", ad: "x.csv" } }));

  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "PEMF_Gecmis.csv", toast);

  const [cagrilanUrl] = mockFetch.mock.calls[0] as [string];
  expect(cagrilanUrl).toContain("kaydet=1");
  expect(tiklamaSayisi).toBe(0); // tarayıcı indirmesi DENENMEDİ
  expect(toastlar).toHaveLength(1);
  expect(toastlar[0][0]).toContain("x.csv");
  expect(toastlar[0][1]).toBe("success");
});

test("KRITIK: var olan sorgu parametresi KORUNUR (& ile eklenir)", async () => {
  // `?session_ids=1,2` varken `?kaydet=1` eklemek URL'i bozar ve sunucu 422 döner.
  mockFetch.mockResolvedValue(yanit({ tur: "application/json", json: { status: "success", yol: "/x", ad: "x.pdf" } }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_pdf?session_ids=1,2", "r.pdf", toast);
  const [u] = mockFetch.mock.calls[0] as [string];
  expect(u).toBe("http://localhost:8000/api/history/export_pdf?session_ids=1,2&kaydet=1");
});

test("KRITIK: kayit YOKSA dosya uretilmez, operatore SOYLENIR", async () => {
  // Eskiden içinde "Veri bulunamadi" yazan bir .csv indiriliyordu; operatör dosyayı
  // açana kadar kayıt olmadığını anlamıyordu.
  mockFetch.mockResolvedValue(yanit({ tur: "application/json", json: { status: "bos", mesaj: "Kayit yok." } }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "g.csv", toast);
  expect(toastlar).toEqual([["Kayit yok.", "info"]]);
  expect(tiklamaSayisi).toBe(0);
});

test("KRITIK: sunucu BEKLENMEYEN yanit verirse SESSIZ DONULMEZ", async () => {
  // ⚠️ Bu, arızanın TEKRARLAMASINI engelleyen kapı: her dal ya başarı ya hata söyler.
  // MUTASYON: son `toast?.("Kaydedilemedi — ...")` satırını sil → KIRMIZI.
  mockFetch.mockResolvedValue(yanit({ tur: "application/json", json: { beklenmeyen: true } }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "g.csv", toast);
  expect(toastlar).toHaveLength(1);
  expect(toastlar[0][1]).toBe("error");
});

test("HTTP hatasi bildirilir", async () => {
  mockFetch.mockResolvedValue(yanit({ ok: false, status: 500 }));
  await downloadFileWithAuth("http://localhost:8000/api/history/export_csv", "g.csv", toast);
  expect(toastlar[0][1]).toBe("error");
  expect(toastlar[0][0]).toContain("500");
});

// ============================================================================
// 2. UZAK BACKEND — tarayıcı indirmesi korunur
// ============================================================================

test("KRITIK: UZAK backend'de kaydet=1 GONDERILMEZ (karsi makinenin masaustune yazardi)", async () => {
  // MUTASYON: `backendBuMakinede`yi `() => true` yap → KIRMIZI.
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockFetch.mockResolvedValue(yanit({ tur: "text/csv" }));

  await downloadFileWithAuth("https://klinik.example.com/api/history/export_csv", "g.csv", toast);

  const [u] = mockFetch.mock.calls[0] as [string];
  expect(u).not.toContain("kaydet=1");
  expect(tiklamaSayisi).toBe(1); // tarayıcı indirmesi YAPILDI
  expect(toastlar[0][1]).toBe("success"); // ⚠️ sessiz dönüş YOK
});

test("KRITIK: tarayici dalinda text/plain DOSYA OLARAK indirilmez", async () => {
  mockConfig.apiBaseUrl = "https://klinik.example.com/api";
  mockFetch.mockResolvedValue(yanit({ tur: "text/plain", metin: "Veri bulunamadi" }));
  await downloadFileWithAuth("https://klinik.example.com/api/history/export_csv", "g.csv", toast);
  expect(tiklamaSayisi).toBe(0);
  expect(toastlar).toEqual([["Veri bulunamadi", "info"]]);
});

// ============================================================================
// 3. YEREL TESPİTİ
// ============================================================================

test.each([
  ["http://localhost:8000/api", true],
  ["http://127.0.0.1:8000/api", true],
  ["https://klinik.example.com/api", false],
  ["http://192.168.1.50:8000/api", false],
])("backendBuMakinede(%s) === %s", (base, beklenen) => {
  mockConfig.apiBaseUrl = base as string;
  expect(backendBuMakinede()).toBe(beklenen);
});

// ============================================================================
// 4. NATIVE (mobil) yolu bozulmadı
// ============================================================================

test("native yolda paylasim menusu acilir ve onbellek TEMIZLENIR", async () => {
  mockPlatformOS = "ios";
  mockDownloadAsync.mockResolvedValue({ uri: "/tmp/r.pdf", status: 200 });
  mockIsSharingAvailable.mockResolvedValue(true);
  mockShareAsync.mockResolvedValue(undefined);

  await downloadFileWithAuth("https://x/api/history/export_pdf?session_ids=1", "r.pdf", toast);

  expect(mockShareAsync).toHaveBeenCalledWith("/tmp/r.pdf");
  // KVKK: paylaşımdan SONRA önbellekteki hasta PDF'i silinmeli.
  expect(mockDeleteAsync).toHaveBeenCalledWith("/tmp/r.pdf", { idempotent: true });
});
