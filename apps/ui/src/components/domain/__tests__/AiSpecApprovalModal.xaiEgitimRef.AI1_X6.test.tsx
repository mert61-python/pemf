// Author: mertaygn, cglrgrkn
/**
 * AI1.X6 (hoca XAI v3, 2026-10) — onay ekranındaki "Dozu en çok belirleyen" satırı yalnız ÖĞRENİLMİŞ ve ETKİLİ girdileri sayar;
 * eğitimde sabit (öğrenilmemiş) girdi ve eğitim aralığı dışındaki değer AYRI satırda söylenir.
 * Ölçülen durum: em_petri'de x/y etkisi 0 iken "Dozu en çok belirleyen: güç bütçesi · konum X · konum Y" yazıyordu; petri organ_id
 * eğitimde sabitti (öğrenilmemiş) ve araştırma hattının gönderdiği organ_id=1 eğitim aralığı dışındaydı — ekranda görünmüyordu.
 */
import { render } from "@testing-library/react-native";
import React from "react";

import { AiSpecApprovalModal, xaiSatirlari } from "../AiSpecApprovalModal";

const SPECS = {
  organ_id: 1,
  duration_minutes: 20,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
  P: [0, 0, 0, 0, 0, 0, 0],
  e_field: 0.07,
};
const bos = () => {};

function ac(meta: any, model?: string) {
  return render(
    <AiSpecApprovalModal visible specs={{ ...SPECS, ...(model ? { model } : {}) } as any} meta={meta} organName="Hedef"
      onApprove={bos} onReject={bos} onDismiss={bos} />,
  );
}

it("öğrenilmemiş girdi 'belirleyen' satırına GİRMEZ, ayrı satırda söylenir; eğitim dışı değer uyarılır", () => {
  const u = ac({
    reliability: 0.8, method: "aruco_pnp",
    xaiSensitivity: [
      { feature: "duty_sum", etki: 0.11 },
      { feature: "organ_id", etki: null, egitim_disi: true, surukleyen: false },
      { feature: "organ_id", etki: null, ogrenilmemis: true },
    ],
  });
  const belirleyen = u.getByText(/Dozu en çok belirleyen/);
  expect(belirleyen.props.children).toBe("Dozu en çok belirleyen: güç bütçesi");
  expect(u.getByText(/Öğrenilmemiş girdi: organ seçimi — model eğitiminde sabitti/)).toBeTruthy();
  expect(u.getByText(/eğitim aralığı dışında \(organ seçimi\)/)).toBeTruthy();
});

it("belirleyenin değeri eğitim aralığı dışındaysa adının yanında söylenir", () => {
  const u = ac({ reliability: 0.8, xaiSensitivity: [{ feature: "z", etki: 0.05, egitim_disi: true }, { feature: "y", etki: 0.01 }] });
  expect(u.getByText(/Dozu en çok belirleyen/).props.children).toBe(
    "Dozu en çok belirleyen: konum Z (eğitim aralığı dışı) · konum Y",
  );
});

it("KARŞIT: düz eski liste (bayraksız) aynen gösterilir; ek satır UYDURULMAZ", () => {
  const u = ac({ reliability: 0.8, xaiSensitivity: [{ feature: "duty_sum", etki: 0.1 }, { feature: "y", etki: 0.05 }] });
  expect(u.getByText(/Dozu en çok belirleyen/).props.children).toBe("Dozu en çok belirleyen: güç bütçesi · konum Y");
  expect(u.queryByText(/Öğrenilmemiş girdi/)).toBeNull();
  expect(u.queryByText(/eğitim aralığı dışında/)).toBeNull();
});

it("xaiSatirlari saf ayrıştırma: belirleyen / eğitim dışı / öğrenilmemiş kümeleri", () => {
  const x = xaiSatirlari(
    [
      { feature: "x", etki: 0.2 },
      { feature: "z", etki: 0.0001, egitim_disi: true, surukleyen: false },
      { feature: "organ_id", etki: null, ogrenilmemis: true },
    ],
    { x: "X", z: "Z", organ_id: "O" },
  );
  expect(x).toEqual({ belirleyen: ["X"], egitimDisi: ["Z"], ogrenilmemis: ["O"] });
});
