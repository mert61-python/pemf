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

/**
 * ARAŞTIRMA ÖNERİSİ (Faz 3, 2026-09-09) — fantom/petri onay ekranı.
 *
 * ⚠️ Model MÜHÜRDEN (`specs.model`) okunur, panelin o anki seçiminden DEĞİL: onay ekranı gerçekten
 * neyin onaylandığını göstermek zorundadır ("fantom önerisini onaylat, kediyi başlat" imkânsız).
 */
const FANTOM = {
  organ_id: 2,
  duration_minutes: 15,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4],
  P: [0, 0, 0, 0, 0, 0, 0],
  e_field: 0.13,
  model: "fantom",
  target_label: "Tümör 2",
  e_cancer: 0.13,
  e_healthy: 0.06,
};

it("KRİTİK: araştırma önerisinde başlık MODEL + HEDEF, alt satırda 'araştırma amaçlı'", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={FANTOM} meta={{ reliability: 0.8, method: "aruco_pnp" }}
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText("AI Seans Önerisi — Fantom Tümör · Tümör 2")).toBeTruthy();
  expect(u.getByText("Araştırma amaçlı model tahmini")).toBeTruthy();
  // 'Organ' etiketi araştırmada YANILTICI: hedef bir tümör odağıdır.
  expect(u.queryByText("Organ")).toBeNull();
  expect(u.getByText("Tümör")).toBeTruthy();
  expect(u.getByText("Tümör 2")).toBeTruthy();
});

it("KRİTİK: konum ve GÖRELİ alan Türkçe ondalıkla; birim UYDURULMAZ", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={FANTOM}
      meta={{ reliability: 0.8, method: "aruco_pnp", x_mm: -42.5, y_mm: 7.25, z_mm: 0 }}
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText("Konum (mm): x -42,5 · y 7,3 · z 0,0")).toBeTruthy();
  const e = u.getByText(/Tahmini alan/);
  const metin = Array.isArray(e.props.children) ? e.props.children.join("") : String(e.props.children);
  expect(metin).toContain("göreli, birimsiz");
  expect(metin).toContain("hedefte 0,13");
  expect(metin).toContain("çevrede 0,06");
  expect(metin).not.toContain("V/m");
});

it("KRİTİK: kabin işareti rozeti + eğitim aralığı (ood) uyarısı görünür", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={FANTOM} meta={{ reliability: 0.8, method: "aruco_pnp", ood: true }}
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText(/kabin işaretiyle doğrulandı/)).toBeTruthy();
  expect(u.getByText(/eğitim aralığı dışında olabilir/)).toBeTruthy();
});

it("KRİTİK: petri önerisinde sınıf ayrımı çekincesi YAZILI (fantomda yok)", () => {
  const petri = { ...FANTOM, model: "petri", target_label: "Kuyu 3 · Kanserli" };
  const u = render(
    <AiSpecApprovalModal visible specs={petri} meta={{ reliability: 0.8, method: "aruco_pnp" }}
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText(/Kanserli\/sağlıklı ayrımı bu modelde sınırlı doğrulanmıştır/)).toBeTruthy();
  const f = render(
    <AiSpecApprovalModal visible specs={FANTOM} meta={{ reliability: 0.8, method: "aruco_pnp" }}
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(f.queryByText(/Kanserli\/sağlıklı ayrımı/)).toBeNull();
});

it("KRİTİK: XAI'da organ_id kanalı araştırmada 'doku tipi' der (kedide 'organ seçimi')", () => {
  const xai = { reliability: 0.8, method: "aruco_pnp", xaiSensitivity: [{ feature: "organ_id", etki: 0.2 }] };
  const a = render(
    <AiSpecApprovalModal visible specs={FANTOM} meta={xai} onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(a.getByText(/doku tipi/)).toBeTruthy();
  const k = render(
    <AiSpecApprovalModal visible specs={SPECS} meta={xai} organName="Karaciğer"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(k.getByText(/organ seçimi/)).toBeTruthy();
});

it("KARŞIT-KANIT: kedi önerisi (model alanı YOK) ekranı BİREBİR eski hâlinde", () => {
  const u = render(
    <AiSpecApprovalModal visible specs={SPECS} meta={{ reliability: 0.8 }} organName="Karaciğer"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
  expect(u.getByText("AI Seans Önerisi")).toBeTruthy();
  expect(u.getByText("Organ")).toBeTruthy();
  expect(u.getByText("E (öngörü)")).toBeTruthy();
  expect(u.queryByText("Araştırma amaçlı model tahmini")).toBeNull();
  expect(u.queryByText(/Tahmini alan/)).toBeNull();
  expect(u.queryByText(/kabin işareti/)).toBeNull();
});
