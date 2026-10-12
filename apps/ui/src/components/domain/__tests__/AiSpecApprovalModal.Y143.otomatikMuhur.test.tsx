// Author: mertaygn, cglrgrkn
/**
 * Y143 (sahip 2026-10-13) — araştırma AI Pro'da "otomatik" hedefle alınan öneri SEÇİLİ hedefin kimliğiyle mühürlenir
 * (backend `meta.otomatik_secim`). Onay ekranı bunu SÖYLER: hekim onayladığı hedefin (ör. «Tümör 2») seans boyunca
 * DEĞİŞMEYECEĞİNİ ve kaybolursa sürüşün DURACAĞINI görür. Alan yoksa (elle seçim / eski backend) satır yok.
 * ⚠️ Beklenen metin BURADA sabittir.
 */
import { render } from "@testing-library/react-native";
import React from "react";

import { AiSpecApprovalModal } from "../AiSpecApprovalModal";

const SPECS = {
  organ_id: 2,
  duration_minutes: 5,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
  P: [0, 0, 0, 0, 0, 0, 0],
  e_field: 0.05,
  model: "fantom",
  target_label: "Tümör 2",
  e_cancer: 0.05,
  e_healthy: 0.01,
};
const bos = () => {};

function ac(meta: Record<string, unknown>) {
  return render(
    <AiSpecApprovalModal visible specs={SPECS} meta={meta} onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
}

it("KRİTİK Y143: otomatik seçimden mühürlenen öneri, seans boyunca YALNIZ o hedefin sürüleceğini söyler", () => {
  const u = ac({ reliability: 0.9, method: "aruco_pnp", otomatik_secim: true });
  const satir = u.getByTestId("ai-onay-otomatik-muhur");
  const metin = Array.isArray(satir.props.children) ? satir.props.children.join("") : String(satir.props.children);
  expect(metin).toContain("Otomatik seçim bu hedefe mühürlendi");
  expect(metin).toContain("Tümör 2");
  expect(metin).toContain("kaybolursa sürüş durur");
});

it("KARŞIT Y143: elle seçimde (alan yok) satır YOK", () => {
  const u = ac({ reliability: 0.9, method: "aruco_pnp" });
  expect(u.queryByTestId("ai-onay-otomatik-muhur")).toBeNull();
});
