/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * YH-A4 · Ö.4-Y8 — uygulama içi onay penceresi açıkken kayan ACİL DURDUR ÜSTTE kalır (web).
 * ==========================================================================
 * Yerli `window.confirm` bütün sayfayı (ve ACİL DURDUR'u) dondururdu; yerine gelen uygulama içi pencere sıradan bir RN-web Modal'ıdır
 * (`position: fixed; z-index: 9999`). Kayan ACİL DURDUR `document.body` portalıyla her Modal'ın üstündedir (D1.E05 · İG-6.6) — bu dosya
 * aynı ölçüyü GERÇEK `OnayPenceresiSaglayici` + GERÇEK köprüyle yapar (soru, GES monte edildikten SONRA açılır: portal kabı DOM'da
 * sonra gelir). Ölçüm yöntemi `GlobalEmergencyStop.D1E05.modalUstu.web.test.tsx` ile aynı (CSS yığın kuralı).
 * ⚠️ MUTASYON: onay penceresi GES katmanının üstüne çıkarılırsa (ör. kendi portalıyla daha yüksek z-index) KIRMIZI.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/components/ui/UstKatman", () => jest.requireActual("@/components/ui/UstKatman.web"));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: { stm: "online", coils: [{ id: 1, running: true, connected: true }], activeTreatment: { isActive: true } },
  }),
}));
jest.mock("@/services/apiClient", () => ({ platformAlert: jest.fn() }));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { View } from "react-native";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { OnayPenceresiSaglayici } from "@/components/ui/OnayPenceresiSaglayici";
import { uygulamaIciOnay } from "@/services/onayKoprusu";

/** BODY düzeyindeki yığın konumu: [z-index, body çocukları arasındaki sıra]. */
function etkinKatman(el: Element): [number, number] {
  let dis: Element = el;
  let z = 0;
  let cur: Element | null = el;
  while (cur && cur !== document.body) {
    const cs = getComputedStyle(cur);
    const konumlu = cs.position !== "" && cs.position !== "static";
    if (konumlu && cs.zIndex !== "" && cs.zIndex !== "auto") z = Number(cs.zIndex);
    dis = cur;
    cur = cur.parentElement;
  }
  return [z, Array.from(document.body.children).indexOf(dis)];
}
const ustte = (a: [number, number], b: [number, number]) => a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);

let kok: Root;
let kap: HTMLDivElement;
beforeEach(() => {
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});
afterEach(async () => {
  await act(async () => kok.unmount());
  document.body.innerHTML = "";
});

it("KRİTİK: uygulama içi onay penceresi açıkken GES'in body düzeyindeki katmanı pencereninkinden ÜSTTE", async () => {
  await act(async () => {
    kok.render(
      <OnayPenceresiSaglayici>
        <View style={{ flex: 1 }}>
          <GlobalEmergencyStop />
        </View>
      </OnayPenceresiSaglayici>
    );
  });
  let soru: Promise<boolean> | null = null;
  await act(async () => {
    soru = uygulamaIciOnay({ baslik: "Mandal sıfırlansın mı?", govde: "Sıfırla", tur: "onay" });
  });
  expect(soru).not.toBeNull(); // aparat: köprü sağlayıcıya bağlı
  const ges = document.querySelector('[aria-label="Acil durdur"]');
  const pencere = document.querySelector('[data-testid="onay-penceresi"]');
  expect(ges).not.toBeNull();
  expect(pencere).not.toBeNull();
  const g = etkinKatman(ges!);
  const p = etkinKatman(pencere!);
  expect(p[0]).toBeGreaterThanOrEqual(9999); // aparat: pencere gerçekten Modal üst katmanında
  expect({ ges: g, pencere: p, ustte: ustte(g, p) }).toEqual({ ges: g, pencere: p, ustte: true });
});
