// Author: mertaygn, cglrgrkn
/**
 * HEKİM ONAY MODALI — XAI SATIRI (Faz 1 kalem 6, 2026-08-26).
 *
 * Backend /ai/pro/propose meta.xaiSensitivity taşıyor ("önerilen dozu en çok ne belirledi",
 * D-kanal hafif duyarlılık). Modal bunu Türkçe etiketlerle göstermeli; alan yoksa (eski
 * backend / XAI hatası zarif düşüşü) satır TAMAMEN gizli.
 */
import { fireEvent, render, within } from "@testing-library/react-native";
import React from "react";

import { AiSpecApprovalModal } from "../AiSpecApprovalModal";

const SPECS = {
  organ_id: 3,
  duration_minutes: 20,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
  P: [0, 0, 0, 0, 0, 0, 0],
  e_field: 0.07,
};

const bos = () => {};

it("KRİTİK: meta.xaiSensitivity → 'Dozu en çok belirleyen' satırı TÜRKÇE etiketlerle görünür", () => {
  const u = render(
    <AiSpecApprovalModal
      visible
      specs={SPECS}
      meta={{
        reliability: 0.8,
        xaiSensitivity: [
          { feature: "duty_sum", etki: 0.148 },
          { feature: "y", etki: 0.056 },
          { feature: "achieved_B", etki: 0.054 },
        ],
      }}
      organName="Karaciğer"
      onApprove={bos}
      onReject={bos}
      onDismiss={bos}
    />,
  );
  const satir = u.getByText(/Dozu en çok belirleyen/);
  const metin = Array.isArray(satir.props.children) ? satir.props.children.join("") : String(satir.props.children);
  expect(metin).toContain("güç bütçesi"); // duty_sum Türkçe etiketi
  expect(metin).toContain("hedef alan"); // achieved_B Türkçe etiketi
});

it("KARŞIT-KANIT: alan yoksa (eski backend / XAI zarif düşüşü) satır GİZLİ", () => {
  const u = render(
    <AiSpecApprovalModal
      visible
      specs={SPECS}
      meta={{ reliability: 0.8 }}
      organName="Karaciğer"
      onApprove={bos}
      onReject={bos}
      onDismiss={bos}
    />,
  );
  expect(u.queryByText(/Dozu en çok belirleyen/)).toBeNull();
});

/**
 * [S5 adım 10 / ekranB-10] ONAY SATIRI SABİT — HASTA GÜVENLİĞİ AKIŞI
 * ------------------------------------------------------------------
 * ÖLÇÜLEN DURUM: kart yüzde tabanlı `maxHeight: "88%"` ile kaydırılamıyordu (Yoga'da çocuklar
 * varsayılan flexShrink:0 → içerik tavanı aşınca TAŞIYOR, kırpılıyor). 8 bobinli öneride ve yatay
 * telefonda (yükseklik 360-430) "Onayla ve Başlat" kartın altında ekran DIŞINDA kalıyordu:
 * "otonom seans onaylanmadan başlamaz" ilkesi doğru çalışıyor ama hekim ONAY VEREMİYORDU.
 *
 * SÖZLEŞME: eylem satırı kaydırma gövdesinin DIŞINDA; onay/red handler'ları değişmedi.
 * ⚠️ MUTASYON: footer tekrar gövdenin içine alınırsa 1. vaka KIRILIR.
 */
const SEKIZ_BOBIN = {
  organ_id: 3,
  duration_minutes: 20,
  coil_ids: [1, 2, 3, 4, 5, 6, 7, 8],
  D: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
  P: [0, 45, 90, 135, 180, 225, 270, 315],
  e_field: 0.07,
};

it("KRİTİK: 'Onayla ve Başlat' kaydırma gövdesinin DIŞINDA (kısa ekranda hep görünür)", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={SEKIZ_BOBIN} organName="Karaciğer"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  const govde = u.getByTestId("ai-onay-govde");
  expect(within(govde).queryByLabelText("Öneriyi onayla ve seansı başlat")).toBeNull();
  expect(u.getByLabelText("Öneriyi onayla ve seansı başlat")).toBeTruthy();
});

it("KRİTİK: onay düğmesi hâlâ onApprove'u çağırıyor (yerleşim değişti, akış değişmedi)", () => {
  let onaylandi = 0;
  const u = render(
    <AiSpecApprovalModal visible specs={SEKIZ_BOBIN} organName="Karaciğer"
      onApprove={() => { onaylandi += 1; }} onReject={bos} onDismiss={bos} />,
  );
  fireEvent.press(u.getByLabelText("Öneriyi onayla ve seansı başlat"));
  expect(onaylandi).toBe(1);
});

it("red gerekçesi alanı da eylem satırında kalır (klavye açıkken erişilir)", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={SEKIZ_BOBIN} organName="Karaciğer"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  fireEvent.press(u.getByLabelText("Öneriyi reddet"));
  const govde = u.getByTestId("ai-onay-govde");
  expect(u.getByLabelText("Red gerekçesi")).toBeTruthy();
  expect(within(govde).queryByLabelText("Red gerekçesi")).toBeNull();
});

it("8 bobinin tamamı tabloda listelenir (iç kaydırıcı kaldırıldı, satır kaybı yok)", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={SEKIZ_BOBIN} organName="Karaciğer"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText("315°")).toBeTruthy();
  expect(u.getByText("Sürülen bobin")).toBeTruthy();
});
