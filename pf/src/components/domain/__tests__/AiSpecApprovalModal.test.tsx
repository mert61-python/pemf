// Author: mertaygn, cglrgrkn
/**
 * HEKİM ONAY MODALI — XAI SATIRI (Faz 1 kalem 6, 2026-08-26).
 *
 * Backend /ai/pro/propose meta.xaiSensitivity taşıyor ("önerilen dozu en çok ne belirledi",
 * D-kanal hafif duyarlılık). Modal bunu Türkçe etiketlerle göstermeli; alan yoksa (eski
 * backend / XAI hatası zarif düşüşü) satır TAMAMEN gizli.
 */
import { render } from "@testing-library/react-native";
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
