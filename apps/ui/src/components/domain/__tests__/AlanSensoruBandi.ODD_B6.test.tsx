// Author: mertaygn, cglrgrkn
/**
 * ODD B-6 (ODK-B keşfi 18-11, sahip 1–2.png) — MLX düştü uyarısı seans / sürüş varken GÖRÜNÜR bantta ("alan sensörü (MLX)").
 * Eskiden yalnız zil listesine sessizce düşüyordu (arayüzde `alanKayip` okuyan 0 satır). Kilitlenen:
 *   - sürüş (aktif seans ya da çalışan bobin) + `alanKayip: true` → bant görünür, kanal numarasıyla, uyarı rolüyle;
 *   - sürüş yok / bayrak yok / bayrak false → bant YOK (seans dışında zil yeter, sahte uyarı yok);
 *   - TR ve EN katalogdan.
 */
let mockSnapshot: unknown = null;
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import { act, render } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { AlanSensoruBandi, alanSensoruBandiMetni } from "@/components/domain/AlanSensoruBandi";

const bobin = (id: number, ek: Record<string, unknown> = {}) => ({ id, running: false, ...ek });

afterEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("tr");
  });
});

it("KRİTİK B-6: seans sürerken MLX düştü → bant GÖRÜNÜR (uyarı rolü, 'alan sensörü (MLX)', kanal)", () => {
  mockSnapshot = { activeTreatment: { isActive: true }, coils: [bobin(1), bobin(6, { alanKayip: true })] };
  const u = render(<AlanSensoruBandi />);
  const bant = u.getByTestId("alan-sensoru-bandi");
  expect(bant.props.accessibilityRole).toBe("alert");
  expect(u.getByText("Alan sensörü (MLX) veri göndermiyor")).toBeTruthy();
  expect(
    u.getByText(
      "Kartta kanal 6. Bobin alanı şu an ölçülemiyor; kart sensörü yeniden arıyor. Düzelmezse sensör kablosunu çıkarıp yeniden takın ya da seansı durdurup kartın gücünü kesip yeniden bağlayın.",
    ),
  ).toBeTruthy();
});

it("KRİTİK B-6: seans kaydı yokken çalışan bobin (sürüş) de bandı açar; İngilizce", async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
  mockSnapshot = { coils: [bobin(1, { running: true }), bobin(6, { alanKayip: true })] };
  const u = render(<AlanSensoruBandi />);
  expect(u.getByText("Field sensor (MLX) is not sending data")).toBeTruthy();
  expect(u.getByText(/Board channel 6\. The coil field cannot be measured right now/)).toBeTruthy();
});

it.each([
  ["sürüş yok", { coils: [bobin(6, { alanKayip: true })] }],
  ["bayrak yok", { activeTreatment: { isActive: true }, coils: [bobin(6)] }],
  ["bayrak false", { activeTreatment: { isActive: true }, coils: [bobin(6, { alanKayip: false })] }],
  ["snapshot yok", null],
  ["bobin listesi yok", { activeTreatment: { isActive: true } }],
])("KARŞIT B-6: %s → bant YOK", (_ad, snap) => {
  mockSnapshot = snap;
  expect(render(<AlanSensoruBandi />).queryByTestId("alan-sensoru-bandi")).toBeNull();
  expect(alanSensoruBandiMetni(snap as never)).toBeNull();
});

it("B-6: birden çok kanal virgülle; kimliği olmayan bobin '?'", () => {
  const m = alanSensoruBandiMetni({ activeTreatment: { isActive: true }, coils: [bobin(6, { alanKayip: true }), { alanKayip: true }] });
  expect(m?.aciklama.startsWith("Kartta kanal 6, ?.")).toBe(true);
});
