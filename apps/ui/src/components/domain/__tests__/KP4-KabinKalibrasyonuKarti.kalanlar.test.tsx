/**
 * KP-4 B1 · src/components/domain/KabinKalibrasyonuKarti.tsx (KD · Y258–Y260, KD-2) — KD testinin kapsamadığı kalan sözleşmeler.
 *  1) Fantom ayarı KAYITLI değerlerle dolu gelir (kalınlık / tümör derinliği / boy × en, sunucudan); alan boşsa doldurulur.
 *  2) Kare görüntüsü kartın ölçülen genişliğinde (iç boşluk düşülerek) ve karenin oranında; 960 px tavan.
 *  3) Eklenen bir konum SİLİNEBİLİR: liste kısalır, eski sonuç düşer, Hesapla yalnız kalan konumları gönderir.
 *  4) "Yeniden kare" yeni kare ister; girilen köşe ölçüleri sıfırlanır (eski kareye ait ölçü yeni kareye taşınmaz).
 *  5) Sonuçta çapraz doğrulama listesi ("—" ölçülemeyen) ve ölçülen lens girilmediyse "lens ölçümsüz" satırı; doğrulama KALDI metni.
 *  6) Kalibrasyon sürerken hazırlık / seans başlarsa (kart KİLİTLENİR) açık kalan "Yeniden kare" düğmesi kamera isteği GÖNDERMEZ
 *     (düğme yalnız kare alınırken pasif; kilidi işleyici uygular — sunucu da 409 verir).
 * GERÇEK: KabinKalibrasyonuKarti, apiClient (zaman aşımı / sessiz / onHttpError sözleşmesi).
 * SAHTE (en alt kat): fetch (yol + yöntem + gövde kaydı).
 */
import React from "react";
import { StyleSheet } from "react-native";
import { act, fireEvent, render, waitFor, type RenderResult } from "@testing-library/react-native";
import i18n from "i18next";

import { KabinKalibrasyonuKarti } from "@/components/domain/KabinKalibrasyonuKarti";
import { spacing } from "@/theme/tokens";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

type Yanit = [number, unknown];
let durum: Record<string, unknown>;
let rota: (yol: string, govde: unknown) => Yanit | undefined;
let fetchSahte: jest.Mock;
let kareNo = 0;

const kare = (bulundu = true) => ({
  kareKimligi: `k${++kareNo}`, genislik: 1920, yukseklik: 1080, image_base64: "QUJD",
  plaka: { bulundu, kuyuSayisi: bulundu ? 24 : 0, kareSayisi: 3, metin: bulundu ? null : "SUNUCU: plaka yok" },
});
const SONUC = {
  gecerli: true, nedenler: [], izdusumHatasiPx: 1.2, olcumUyumuMm: 5, yayilimCm: 25,
  konumlar: [
    { koseSapmasiMm: [3, null, 2, null], kuyuIzdusumPx: 1.1, merkezCm: [12, 10] },
    { koseSapmasiMm: [1, 2, 3, 4], kuyuIzdusumPx: 1.3, merkezCm: [38, 20] },
  ],
  caprazDogrulamaCm: [1.24, null], hesaplananLensCm: [25.06, 12, 38.81], olculenLensCm: null,
  lensYatayFarkiCm: null, lensDikeyFarkiCm: null, lensUyarisi: false,
  gorusAlani: null, sahne: null,
  esikler: { izdusumPx: 3, lensCm: 2, lensDikeyCm: 3, olcumMm: 10, yayilimCm: 20, konumAsgari: 2 },
};
const GECERLI = {
  var: true, gecerli: true, tarih: "2026-11-10T15:00:00+0300", konumSayisi: 2, izdusumHatasiPx: 1.2, lensFarkiCm: 1,
  kameraAdi: "FHD Camera", kameraVidPid: "VID_1BCF&PID_28C4", olculenLensTabanCm: 36.5, sahneDenetimi: true, eski: false,
  tabanYukseltmesiCm: 0,
};

function yolu(url: unknown): string {
  return String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^\/api/, "");
}
const postlar = (yol: string) =>
  fetchSahte.mock.calls
    .filter((c) => yolu(c[0]) === yol && (c[1] as { method?: string } | undefined)?.method === "POST")
    .map((c) => JSON.parse(String((c[1] as { body?: string }).body ?? "null")));

beforeEach(() => {
  kareNo = 0;
  durum = { var: false, gecerli: false, hataMetni: "SUNUCU: kalibrasyon yok" };
  rota = () => undefined;
  fetchSahte = jest.fn(async (url: unknown, init: { method?: string; body?: string } = {}) => {
    const yol = yolu(url);
    let y: Yanit = [200, {}];
    if (yol === "/ai/pro/kalibrasyon" && (init.method ?? "GET") === "GET") y = [200, durum];
    else {
      const govde = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
      const o = rota(yol, govde);
      if (o) y = o;
      else if (yol === "/ai/pro/kalibrasyon/kare") y = [200, kare()];
    }
    return { ok: y[0] < 400, status: y[0], json: async () => JSON.parse(JSON.stringify(y[1])), text: async () => JSON.stringify(y[1]),
      headers: { get: () => "application/json" } };
  });
  (global as unknown as { fetch: unknown }).fetch = fetchSahte;
});

function olc(e: RenderResult, koseler: number[], taban = 10) {
  for (const i of koseler) {
    fireEvent.changeText(e.getByTestId(`kabin-kalibrasyonu-sol-${i}`), `${taban + i}`);
    fireEvent.changeText(e.getByTestId(`kabin-kalibrasyonu-on-${i}`), `${20 + i}`);
  }
}
async function konumEkle(e: RenderResult, koseler: number[], taban: number) {
  await e.findByTestId("kabin-kalibrasyonu-kare");
  olc(e, koseler, taban);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-konum-ekle")); });
}

it("KRİTİK: fantom ayarı kayıtlı değerlerle (sunucudan) dolu gelir; taban uzaklığı lens − yükseltme", async () => {
  durum = { ...GECERLI, olculenLensTabanCm: 36.5, tabanYukseltmesiCm: 2,
    fantom: { kalinlikCm: 1.5, tumorDerinligiCm: 0.4, boyCm: [6, 4.5] } };
  const e = render(<KabinKalibrasyonuKarti model="fantom" />);
  await waitFor(() => expect(e.getByTestId("kabin-kalibrasyonu-fantom-kalinlik").props.value).toBe("1.5"));
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-derinlik").props.value).toBe("0.4");
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-boy").props.value).toBe("6");
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-en").props.value).toBe("4.5");
  expect(e.getByTestId("kabin-kalibrasyonu-taban-uzaklik").props.value).toBe("34.5");
});

it("KARŞIT: kayıtta fantom boyutu yoksa (yalnız kalınlık) diğer alanlar BOŞ kalır", async () => {
  durum = { ...GECERLI, fantom: { kalinlikCm: 2, tumorDerinligiCm: null, boyCm: null } };
  const e = render(<KabinKalibrasyonuKarti model="fantom" />);
  await waitFor(() => expect(e.getByTestId("kabin-kalibrasyonu-fantom-kalinlik").props.value).toBe("2"));
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-derinlik").props.value).toBe("");
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-boy").props.value).toBe("");
  expect(e.getByTestId("kabin-kalibrasyonu-fantom-en").props.value).toBe("");
});

it("KRİTİK: kare kartın ölçülen genişliğinde (iç boşluk düşülür), karenin oranında; 960 px tavan", async () => {
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  await act(async () => { fireEvent.press(await e.findByTestId("kabin-kalibrasyonu-baslat")); });
  const boyut = () => {
    const st = StyleSheet.flatten(e.getByTestId("kabin-kalibrasyonu-kare").props.style) as { width: number; height: number };
    return [st.width, Math.round(st.height)];
  };
  expect(boyut()).toEqual([320, 180]); // ölçüm yokken 320 px
  await act(async () => {
    fireEvent(e.getByTestId("kabin-kalibrasyonu"), "layout", { nativeEvent: { layout: { width: 640 + 2 * spacing.md, height: 900 } } });
  });
  expect(boyut()).toEqual([640, 360]);
  await act(async () => {
    fireEvent(e.getByTestId("kabin-kalibrasyonu"), "layout", { nativeEvent: { layout: { width: 3000, height: 900 } } });
  });
  expect(boyut()).toEqual([960, 540]);
});

it("KRİTİK: eklenen konum SİLİNİR — liste kısalır, eski sonuç düşer, Hesapla yalnız kalanları gönderir", async () => {
  rota = (yol) => (yol === "/ai/pro/kalibrasyon/hesapla" ? [200, SONUC] : undefined);
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  await act(async () => { fireEvent.press(await e.findByTestId("kabin-kalibrasyonu-baslat")); });
  await konumEkle(e, [0, 2], 10); // k1
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-kare-al")); });
  await konumEkle(e, [0, 1, 2, 3], 35); // k2
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-hesapla")); });
  await e.findByTestId("kabin-kalibrasyonu-sonuc");

  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-konum-sil-0")); });
  expect(e.queryByTestId("kabin-kalibrasyonu-sonuc")).toBeNull();
  expect(e.queryByTestId("kabin-kalibrasyonu-konum-1")).toBeNull();
  expect([e.getByTestId("kabin-kalibrasyonu-konum-0").findAllByType(require("react-native").Text)[0].props.children].flat().join(""))
    .toBe(T("ai.kalibrasyon.konum.satir", { n: 1, kose: 4 }));
  expect(e.getByTestId("kabin-kalibrasyonu-hesapla").props.accessibilityState?.disabled).toBe(true);

  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-kare-al")); });
  await konumEkle(e, [1, 3], 50); // k3
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-hesapla")); });
  await e.findByTestId("kabin-kalibrasyonu-sonuc");
  const hesap = postlar("/ai/pro/kalibrasyon/hesapla");
  expect(hesap).toHaveLength(2);
  expect(hesap[1].konumlar.map((k: { kareKimligi: string }) => k.kareKimligi)).toEqual(["k2", "k3"]);
});

it("KRİTİK: 'Yeniden kare' yeni kare ister; girilen köşe ölçüleri SIFIRLANIR", async () => {
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  await act(async () => { fireEvent.press(await e.findByTestId("kabin-kalibrasyonu-baslat")); });
  await e.findByTestId("kabin-kalibrasyonu-kare");
  olc(e, [0, 1], 10);
  expect(e.getByTestId("kabin-kalibrasyonu-sol-0").props.value).toBe("10");
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-yeniden-kare")); });
  await waitFor(() => expect(postlar("/ai/pro/kalibrasyon/kare")).toHaveLength(2));
  await waitFor(() => expect(e.getByTestId("kabin-kalibrasyonu-sol-0").props.value).toBe(""));
  expect(e.getByTestId("kabin-kalibrasyonu-on-1").props.value).toBe("");
  expect(e.getByTestId("kabin-kalibrasyonu-konum-ekle").props.accessibilityState?.disabled).toBe(true);
});

it("KRİTİK: sonuçta çapraz doğrulama listesi ('—' ölçülemeyen) ve ölçülen lens yoksa 'lens ölçümsüz' satırı", async () => {
  rota = (yol) => (yol === "/ai/pro/kalibrasyon/hesapla" ? [200, SONUC] : undefined);
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  await act(async () => { fireEvent.press(await e.findByTestId("kabin-kalibrasyonu-baslat")); });
  await konumEkle(e, [0, 2], 10);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-kare-al")); });
  await konumEkle(e, [0, 1, 2, 3], 35);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-hesapla")); });
  await e.findByTestId("kabin-kalibrasyonu-sonuc");
  expect(postlar("/ai/pro/kalibrasyon/hesapla")[0].lens).toBeNull(); // lens girilmedi
  expect(e.getByTestId("kabin-kalibrasyonu-capraz").props.children).toBe(T("ai.kalibrasyon.sonuc.capraz", { liste: "1.2 / —" }));
  expect(e.getByTestId("kabin-kalibrasyonu-lens").props.children)
    .toBe(T("ai.kalibrasyon.sonuc.lensOlcumsuz", { h: "25.1 / 12.0 / 38.8" }));
});

it("KRİTİK: doğrulama KALDI — merkez farkı, ölçülen köşelerin farkı (ölçülmeyen atlanır) ve sınır sunucudan", async () => {
  durum = GECERLI;
  rota = (yol) =>
    yol === "/ai/pro/kalibrasyon/dogrula" ? [200, { farkCm: [2.14, null, null, 4], merkezFarkCm: 3.36, gecti: false, esikCm: 1 }] : undefined;
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  const dogrulaBaslat = await e.findByTestId("kabin-kalibrasyonu-dogrula-baslat");
  await act(async () => { fireEvent.press(dogrulaBaslat); });
  await e.findByTestId("kabin-kalibrasyonu-kare");
  olc(e, [0, 3], 10);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-dogrula")); });
  const s = await e.findByTestId("kabin-kalibrasyonu-dogrulama-sonuc");
  expect(s.props.children).toBe(T("ai.kalibrasyon.dogrulamaKaldi", { merkez: "3,4", farklar: "1: 2,1 · 4: 4,0", esik: 1 }));
});

it("KRİTİK: kalibrasyon sürerken kart kilitlenirse 'Yeniden kare' kamera isteği GÖNDERMEZ", async () => {
  const e = render(<KabinKalibrasyonuKarti model="petri" />);
  await act(async () => { fireEvent.press(await e.findByTestId("kabin-kalibrasyonu-baslat")); });
  await e.findByTestId("kabin-kalibrasyonu-kare");
  expect(postlar("/ai/pro/kalibrasyon/kare")).toHaveLength(1);
  e.rerender(<KabinKalibrasyonuKarti model="petri" kilitli />); // hazırlık başladı
  expect(e.getByText(T("ai.kalibrasyon.kilitli"))).toBeTruthy();
  // KP-5 · 7 (gözlem → düzeltme): kilitliyken düğme PASİF GÖRÜNÜR (öteki kart düğmeleriyle aynı) — basınca sessizce hiçbir şey olmaması yerine.
  expect(e.getByTestId("kabin-kalibrasyonu-yeniden-kare").props.accessibilityState?.disabled).toBe(true);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-yeniden-kare")); });
  expect(postlar("/ai/pro/kalibrasyon/kare")).toHaveLength(1);
  e.rerender(<KabinKalibrasyonuKarti model="petri" />); // kilit kalktı → yine çalışır
  expect(e.getByTestId("kabin-kalibrasyonu-yeniden-kare").props.accessibilityState?.disabled).toBe(false);
  await act(async () => { fireEvent.press(e.getByTestId("kabin-kalibrasyonu-yeniden-kare")); });
  await waitFor(() => expect(postlar("/ai/pro/kalibrasyon/kare")).toHaveLength(2));
});
