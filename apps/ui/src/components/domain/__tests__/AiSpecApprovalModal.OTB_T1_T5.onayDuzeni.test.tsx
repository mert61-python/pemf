// Author: mertaygn, cglrgrkn
/**
 * OTB T-1 / T-2 / T-3 / T-4 / T-5 / T-13 (ODM tezgâhı 19-11, onay penceresi "buraya bir düzen şart"):
 *  - T-1: "Doz (en çok X)" kip (Kuyucuk ↔ Tüm petri) ya da haritadan seçilen kuyu değişince yenilenmiyordu (B4'ün 1,77'si Tüm petride
 *    kaldı) → seçili kip / kuyunun tavanı önerinin `tavanlar`ından (sunucu, plan tavanıyla aynı hesap); bilinmiyorsa sayı yok.
 *  - T-2 / T-3: tavan modelin ulaşabildiği; fizik tavanı ve uygulanan fizik düzeltmesi ayrıca söylenir.
 *  - T-4: kirliyken harita ÖNCEKİ planın sayılarını gösteriyordu (sahip haritadaki sayıyı doz diye girdi) → sayılar GİZLİ, "Önceki plan
 *    (<hedef>)" görünür.
 *  - T-5: kirliyken başlık / hedef / mühür metni ESKİ hedefi söylüyordu ("Petri Kuyu · Kuyu B4", "yalnız «Kuyu C2» sürülür") → SEÇİLİ kip
 *    / kuyu; mühür metni kirliyken yok.
 *  - T-13: konum 2 dk'dan eskiyken "Onayla ve Başlat" ETKİNDİ → PASİF + neden ("Konumu tazele ve yeniden hesapla").
 * Düzen ODD B-2 testiyle aynı. TR + EN.
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { AiSpecApprovalModal } from "../AiSpecApprovalModal";

const KUYULAR = Array.from({ length: 24 }, (_, i) => ({
  etiket: `${"ABCD"[Math.floor(i / 6)]}${(i % 6) + 1}`,
  px: [100 + 40 * (i % 6), 60 + 40 * Math.floor(i / 6)],
  mT: 0.5 + 0.01 * i,
  secili: i === 9, // B4
}));
const TAVANLAR = { TUM_PETRI: 1.4, KUYUCUK: { B4: 1.59, C2: 1.31 } };
const ODAK = {
  kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.61, tavan_mT: 1.59, fizik_tavan_mT: 1.81, cevre_mT: 0.48, oran: 1.27, pay_yuzde: 7.4,
  kuyular: KUYULAR, tavanlar: TAVANLAR,
};
const SPECS = {
  organ_id: 9, duration_minutes: 5, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.2, 0.1, 0.3, 0, 0, 0.1, 0.2], P: [108, 0, 36, 0, 0, 72, 180],
  e_field: 0, model: "petri", target_label: "Kuyu B4",
};

function ac(ek: Record<string, unknown> = {}, odak: Record<string, unknown> = ODAK, meta: Record<string, unknown> = {}) {
  return render(
    <AiSpecApprovalModal
      visible
      specs={{ ...SPECS, odak } as never}
      meta={{ reliability: 0.9, method: "aruco_pnp", ...meta }}
      onApprove={jest.fn()}
      onReject={() => {}}
      onDismiss={() => {}}
      onYenidenHesapla={() => {}}
      {...ek}
    />
  );
}
const dozEtiketi = (u: ReturnType<typeof render>) => JSON.stringify(u.getByTestId("odak-doz-etiket").props.children);
const metin = (u: ReturnType<typeof render>) => JSON.stringify(u.toJSON());

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK T-1: 'en çok' kip ve kuyu değişince YENİLENİR (önerinin tavanlarıyla); bilinmeyen seçimde sayı YOK", () => {
  const u = ac();
  expect(dozEtiketi(u)).toContain("1,59");
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  expect(dozEtiketi(u)).toContain("1,40");
  expect(dozEtiketi(u)).not.toContain("1,59");
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  fireEvent.press(u.getByTestId("odak-kuyu-C2"));
  expect(dozEtiketi(u)).toContain("1,31");
  fireEvent.press(u.getByTestId("odak-kuyu-A1")); // tavanı bilinmeyen kuyu
  expect(dozEtiketi(u)).not.toMatch(/\d,\d\d/);
  // seçilen kuyunun tavanı doğrulamayı da belirler
  fireEvent.press(u.getByTestId("odak-kuyu-C2"));
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "1,5");
  expect(u.getByTestId("odak-doz-hata")).toBeTruthy();
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "1,3");
  expect(u.queryByTestId("odak-doz-hata")).toBeNull();
});

it("T-1: Tüm petri önerisinden KUYUCUK'a geçip kuyu seçilmediyse 'önce haritadan kuyu seçin'", () => {
  const u = ac({}, { ...ODAK, kip: "TUM_PETRI", tavan_mT: 1.4, kuyular: KUYULAR.map((k) => ({ ...k, secili: false })) });
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  expect(dozEtiketi(u)).toContain("haritadan bir kuyu");
});

it("T-2 / T-3: fizik tavanı ve uygulanan fizik düzeltmesi SÖYLENİR", () => {
  const u = ac({}, { ...ODAK, duzeltme: { ilk_beklenen_mT: 0.52, kat: 1.15 } });
  expect(JSON.stringify(u.getByTestId("odak-fizik-tavan").props.children)).toMatch(/1,59.*1,81/);
  expect(JSON.stringify(u.getByTestId("odak-duzeltme").props.children)).toMatch(/1,15.*0,52/);
});

it("KRİTİK T-4: kirliyken önceki planın SAYILARI gizli, 'Önceki plan (<hedef>)' görünür", () => {
  const u = ac();
  expect(metin(u)).toContain("0,59"); // B4 kuyusunun planlı değeri
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  const m = metin(u);
  expect(m).not.toContain("0,59");
  expect(m).not.toContain("Beklenen (fizik denetimi)");
  expect(JSON.stringify(u.getByTestId("odak-onceki-plan").props.children)).toContain("Kuyu B4");
});

it("KRİTİK T-5: kirliyken başlık ve hedef SEÇİMİ söyler; mühür metni kirliyken YOK", () => {
  const u = ac({ hedefGosterim: "Kuyu B4" }, ODAK, { otomatik_secim: true });
  expect(metin(u)).toContain("Kuyu B4");
  expect(u.getByTestId("ai-onay-otomatik-muhur")).toBeTruthy();
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  const m = metin(u);
  expect(m).toContain("Tüm petri");
  expect(u.queryByTestId("ai-onay-otomatik-muhur")).toBeNull();
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  fireEvent.press(u.getByTestId("odak-kuyu-C2"));
  expect(metin(u)).toContain("Kuyu C2");
});

it("KRİTİK T-13: konum 2 dk'dan eskiyken Onayla PASİF ve NEDEN söylenir; taze konumda AÇIK", () => {
  const eski = ac({ konumEski: true, onKonumTazele: () => {} });
  expect(eski.getByTestId("ai-onay-onayla").props.accessibilityState.disabled).toBe(true);
  expect(eski.getByTestId("ai-onay-konum-eski")).toBeTruthy();
  const taze = ac({ konumEski: false, onKonumTazele: () => {} });
  expect(taze.getByTestId("ai-onay-onayla").props.accessibilityState.disabled).toBe(false);
  expect(taze.queryByTestId("ai-onay-konum-eski")).toBeNull();
});

it("EN: yeni metinler İngilizce (Türkçe harf yok)", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const u = ac({ konumEski: true, onKonumTazele: () => {} }, { ...ODAK, duzeltme: { ilk_beklenen_mT: 0.52, kat: 1.15 } });
  for (const id of ["odak-fizik-tavan", "odak-duzeltme", "ai-onay-konum-eski"]) {
    expect(JSON.stringify(u.getByTestId(id).props.children)).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/);
  }
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  expect(JSON.stringify(u.getByTestId("odak-onceki-plan").props.children)).toMatch(/Previous plan/);
  expect(metin(u)).toContain("Whole well plate");
});
