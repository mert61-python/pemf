// Author: mertaygn, cglrgrkn
/**
 * TD6 · K12 (tezgâh Oturum 13) — mandal bandı NEDENE GÖRE EYLEM söyler.
 *
 * ÖLÇÜLEN: "ACİL DURDUR düğmesi" · "kart komutları reddetti" · "STM32 bağlantı kaybı" — hepsi aynı cümleyi alıyordu ("Bobinlerin
 * durduğunu cihazda kontrol edin… Sıfırla"); kart reddinde NE reddedildiği, kopmada kablonun kontrol edilmesi gerektiği yoktu.
 * SÖZLEŞME: kablo (bağlantı kaybı / watchdog) → "USB kablosunu kontrol edin."; kart reddi → backend'in `eylem` metni (duty reddinde
 * K3: "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; …"). "Sıfırla" bilinçli eylemi ve "sıfırlama bobinleri başlatmaz" KALIR (Y4).
 */
let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(), platformConfirm: jest.fn(), platformAlert: jest.fn() }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import React from "react";
import { render } from "@testing-library/react-native";
import { EstopMandalBandi, mandalEylemi } from "@/components/ui/EstopMandalBandi";

const K3 =
  "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi; seans DURDURULDU. Duty'yi %50 veya altına indirin " +
  "(ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın), sonra 'Sıfırla'ya basın ve yeniden başlatın.";

const bant = (estopMandali: Record<string, unknown>) => {
  mockSnapshot = { coils: [], activeTreatment: { isActive: false }, estopMandali };
  const u = render(<EstopMandalBandi />);
  return String(u.getByText(/^Neden:/).props.children);
};

it("KRITIK K12: bağlantı kaybı → 'USB kablosunu kontrol edin'", () => {
  const m = bant({ aktif: true, neden: "stm_disconnected" });
  expect(m).toContain("USB kablosunu kontrol edin.");
  expect(m).toContain('önce "Sıfırla"');
  expect(bant({ aktif: true, neden: "onceki_oturum:stm_watchdog_timeout" })).toContain("USB kablosunu kontrol edin.");
});

it("KRITIK K12: kart reddi → backend'in K3 metni; 'Sıfırla' İKİ KEZ yazılmaz", () => {
  const m = bant({ aktif: true, neden: "stm_komut_reddi", eylem: K3 });
  expect(m).toContain(K3);
  expect(m).not.toContain('önce "Sıfırla"');
  expect(m).toContain("Sıfırlama bobinleri başlatmaz.");
});

it("K12: kart reddi eylemsizse (eski backend / önceki oturum) yine EYLEM söyler; düğme nedeni kablo DEMEZ", () => {
  expect(bant({ aktif: true, neden: "stm_komut_reddi" })).toMatch(/duty \/ sürüş kipi/);
  const d = bant({ aktif: true, neden: "manual" });
  expect(d).not.toContain("USB");
  expect(d).toContain('önce "Sıfırla"');
  expect(mandalEylemi("manual")).toBe("");
});
