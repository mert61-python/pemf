// Author: mertaygn, cglrgrkn
/**
 * ODD B-2 (ODK-B keşfi 18-11, kum havuzu 08 / 10 / 11 / 12): onay penceresinde kip / doz / kuyu değişip "Yeniden hesapla"ya basılmadan
 * "Onayla ve Başlat" SON HESAPLANAN öneriyi başlatıyordu (ekrandaki seçimle uyuşmaz); kip değişince tavan etiketi ve doğrulama ÖTEKİ kipin
 * tavanıyla kalıyordu (Kuyucuk → Tüm petri: "en çok 2,00"; Tüm petri → Kuyucuk: "en çok 1,70" → 1,9 girilemiyor).
 * SÖZLEŞME: seçim önerinin planından farklıysa (KİRLİ) onay PASİF + "önce Yeniden hesapla" uyarısı; harita ve bobin tablosu "önceki plan"
 * (soluk + etiket). Tavan YALNIZ hesaplandığı kipte söylenir / denetlenir. Yeni öneri gelince temiz. TR + EN. Düzen ODK testiyle aynı.
 */
import { act, fireEvent, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { AiSpecApprovalModal } from "../AiSpecApprovalModal";

const KUYULAR = Array.from({ length: 24 }, (_, i) => ({
  etiket: `${"ABCD"[Math.floor(i / 6)]}${(i % 6) + 1}`,
  px: [100 + 40 * (i % 6), 60 + 40 * Math.floor(i / 6)],
  mT: 0.5 + 0.01 * i,
  secili: i === 8,
}));
const ODAK = { kip: "KUYUCUK", doz_mT: 0.6, beklenen_mT: 0.61, tavan_mT: 1.7, cevre_mT: 0.48, oran: 1.27, pay_yuzde: 7.4, kuyular: KUYULAR };
const SPECS = {
  organ_id: 9, duration_minutes: 5, coil_ids: [1, 2, 3, 4, 5, 6, 7], D: [0.2, 0.1, 0.3, 0, 0, 0.1, 0.2], P: [108, 0, 36, 0, 0, 72, 180],
  e_field: 0, model: "petri", target_label: "Kuyu B3",
};

function ac(onApprove = jest.fn(), odak: Record<string, unknown> = ODAK) {
  const el = (o: Record<string, unknown>) => (
    <AiSpecApprovalModal
      visible
      specs={{ ...SPECS, odak: o } as never}
      meta={{ reliability: 0.9, method: "aruco_pnp" }}
      onApprove={onApprove}
      onReject={() => {}}
      onDismiss={() => {}}
      onYenidenHesapla={() => {}}
    />
  );
  const u = render(el(odak));
  return { u, yeniOneri: (o: Record<string, unknown>) => u.rerender(el(o)) };
}
const onay = (u: ReturnType<typeof render>) => u.getByTestId("ai-onay-onayla");
const metin = (u: ReturnType<typeof render>) => JSON.stringify(u.toJSON());

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK B-2: temiz pencerede Onayla AÇIK; kip değişince PASİF + uyarı + harita / tablo 'önceki plan' — basılsa da başlatmaz", () => {
  const onApprove = jest.fn();
  const { u } = ac(onApprove);
  expect(onay(u).props.accessibilityState.disabled).toBe(false);
  expect(u.queryByTestId("ai-onay-kirli")).toBeNull();
  expect(u.queryByTestId("odak-harita-eski")).toBeNull();
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  expect(onay(u).props.accessibilityState.disabled).toBe(true);
  expect(u.getByTestId("ai-onay-kirli")).toBeTruthy();
  expect(u.getByTestId("odak-kirli")).toBeTruthy();
  expect(u.getByTestId("odak-harita-eski")).toBeTruthy();
  expect(u.getByTestId("ai-onay-tablo-eski")).toBeTruthy();
  fireEvent.press(onay(u));
  expect(onApprove).not.toHaveBeenCalled();
  // geri alınca temiz
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  expect(onay(u).props.accessibilityState.disabled).toBe(false);
  fireEvent.press(onay(u));
  expect(onApprove).toHaveBeenCalledTimes(1);
});

it("KRİTİK B-2: doz değişince ve haritadan başka kuyu seçilince de KİRLİ; geçersiz doz da onaylanamaz", () => {
  const { u } = ac();
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,7");
  expect(onay(u).props.accessibilityState.disabled).toBe(true);
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,60");
  expect(onay(u).props.accessibilityState.disabled).toBe(false);
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "abc");
  expect(onay(u).props.accessibilityState.disabled).toBe(true);
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0,6");
  fireEvent.press(u.getByTestId("odak-kuyu-C6"));
  expect(onay(u).props.accessibilityState.disabled).toBe(true);
  expect(u.getByTestId("odak-harita-eski")).toBeTruthy();
});

it("KRİTİK B-2: tavan YALNIZ hesaplandığı kipte — kip değişince 'en çok' sayısı yok, eski kipin tavanıyla doz REDDEDİLMEZ", () => {
  const { u } = ac();
  expect(u.getByTestId("odak-doz-etiket").props.children).toBe("Doz (mT, en çok 1,70)");
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  expect(u.getByTestId("odak-doz-etiket").props.children).toBe(
    "Doz (mT) — bu kipin üst sınırı Yeniden hesapla'dan sonra görünür",
  );
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "1,9"); // Kuyucuk tavanının (1,70) üstü — Tüm petri'de geçerli olabilir
  expect(u.getByTestId("odak-yeniden-hesapla").props.accessibilityState.disabled).toBe(false);
  expect(u.queryByTestId("odak-doz-hata")).toBeNull();
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "0");
  expect(metin(u)).toContain("0'dan büyük bir doz (mT) girin.");
  // aynı kipte tavan denetimi AYNEN
  fireEvent.press(u.getByTestId("odak-kip-KUYUCUK"));
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "1,9");
  expect(u.getByTestId("odak-yeniden-hesapla").props.accessibilityState.disabled).toBe(true);
  expect(metin(u)).toContain("0'dan büyük ve en çok 1,70 mT bir doz girin.");
});

it("KRİTİK B-2: yeni öneri (yeniden hesaplanan plan) gelince pencere TEMİZ ve yeni kipin tavanı", () => {
  const { u, yeniOneri } = ac();
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  fireEvent.changeText(u.getByTestId("odak-doz-girdi"), "1,9");
  expect(onay(u).props.accessibilityState.disabled).toBe(true);
  act(() => yeniOneri({ ...ODAK, kip: "TUM_PETRI", doz_mT: 1.9, tavan_mT: 2.0, kuyular: KUYULAR.map((k) => ({ ...k, secili: false })) }));
  expect(onay(u).props.accessibilityState.disabled).toBe(false);
  expect(u.queryByTestId("ai-onay-kirli")).toBeNull();
  expect(u.getByTestId("odak-doz-etiket").props.children).toBe("Doz (mT, en çok 2,00)");
});

it("KRİTİK B-2: İngilizce uyarılar", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  const { u } = ac();
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  const m = metin(u);
  expect(m).toContain("Approval is disabled: press Recalculate first (what you approve must be the plan shown).");
  expect(m).toContain("Changes not applied yet: the map and coil table still show the previous plan. Press Recalculate to apply them.");
  expect(m).toContain("Previous plan — not recalculated");
  expect(m).toContain("Dose (mT) — the limit for this mode is shown after Recalculate");
});

it("KRİTİK B-2: yeni önerinin kipi yerel seçimden FARKLIYSA pencere öneriyi izler (seçili kip = önerinin kipi, temiz)", () => {
  const { u, yeniOneri } = ac();
  fireEvent.press(u.getByTestId("odak-kip-TUM_PETRI"));
  act(() => yeniOneri({ ...ODAK, doz_mT: 0.7 })); // ör. konum tazelenip AYNI kip (KUYUCUK) ile yeniden önerildi
  expect(u.getByTestId("odak-kip-KUYUCUK").props.accessibilityState.checked).toBe(true);
  expect(u.getByTestId("odak-kip-TUM_PETRI").props.accessibilityState.checked).toBe(false);
  expect(onay(u).props.accessibilityState.disabled).toBe(false);
  expect(u.getByTestId("odak-doz-girdi").props.value).toBe("0,70");
});
