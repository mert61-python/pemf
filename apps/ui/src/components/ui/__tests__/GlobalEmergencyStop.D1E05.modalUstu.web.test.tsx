/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * D1.E05 · İG-6.6 — web'de kayan ACİL DURDUR her açık Modal'ın ÜSTÜNDE kalır.
 * ==========================================================================
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.6, gerçek web paketi + headless Chrome, `elementFromPoint`): Seans Detayı Modal'ı
 * açıkken GES'in merkezindeki eleman Modal kapsayıcısıydı → E-stop isteği 0, bobin sürmeye devam etti. Neden:
 * react-native-web Modal'ı `document.body`'ye `position: fixed; z-index: 9999` portalla çizer; GES uygulama kökünde,
 * RN-web `View`'larının `z-index: 0` yığın bağlamında kalır.
 *
 * Ölçüm (jsdom, layout YOK): GERÇEK `react-native-web` + GERÇEK `Modal` + GERÇEK `GlobalEmergencyStop`; her elemanın BODY
 * düzeyindeki etkin katmanı CSS yığın kuralıyla hesaplanır (bodye en yakın, konumlu ve z-index'i `auto` olmayan ata
 * yığın bağlamını belirler; eşitlikte DOM'da SONRA gelen üsttedir). RN-web'in atomik CSS'i jsdom `getComputedStyle`'da
 * çözülür (ölçüldü: Modal kapsayıcısı `fixed z=9999`, View `relative z=0`). Gerçek tarayıcıda aynı düzeltme (portal +
 * en üst katman) aday raporunun mutant 66'sında ölçüldü: GES isabet aldı, 4 durdurma isteği gitti, tel STOP.
 * `UstKatman` jest'te native çözülür → bu dosyada `.web` sürümüne eşlenir (Metro web paketinde kendisi seçilir).
 *
 * ⚠️ MUTASYON: GES `UstKatman`'dan çıkarılırsa ya da web katman değeri Modal'ın altına inerse KIRMIZI.
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
import { Modal, Text, View } from "react-native";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

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

describe("D1.E05 / İG-6.6 — web: kayan ACİL DURDUR açık Modal'ın üstünde", () => {
  it("KRİTİK: Modal açıkken GES'in body düzeyindeki katmanı Modal'ınkinden ÜSTTE", async () => {
    await act(async () => {
      kok.render(
        <View style={{ flex: 1 }}>
          <GlobalEmergencyStop />
          <Modal visible transparent>
            <View>
              <Text>Seans Detayı</Text>
            </View>
          </Modal>
        </View>
      );
    });
    const ges = document.querySelector('[aria-label="Acil durdur"]');
    const modal = Array.from(document.querySelectorAll("div")).reverse().find((d) => d.textContent === "Seans Detayı");
    expect(ges).not.toBeNull();
    expect(modal).toBeDefined();
    const g = etkinKatman(ges!);
    const m = etkinKatman(modal!);
    expect(m[0]).toBeGreaterThanOrEqual(9999); // aparat: RN-web Modal'ı gerçekten üst katmanda
    expect({ ges: g, modal: m, ustte: ustte(g, m) }).toEqual({ ges: g, modal: m, ustte: true });
  });

  it("KRİTİK: Modal SONRADAN monte edilse de (portal kabı DOM'da GES'ten SONRA) GES üstte kalır", async () => {
    // Gerçek uygulamada kabuk (GES) önce, ekranın Modal'ı sonra monte edilir → RN-web Modal kabı body'de GES'ten
    // SONRA gelir; eşit katmanda sonra gelen üsttedir. Bu kol katman değerinin Modal'ınkinden BÜYÜK olmasını ölçer.
    const Agac = ({ acik }: { acik: boolean }) => (
      <View style={{ flex: 1 }}>
        <GlobalEmergencyStop />
        {acik ? (
          <Modal visible transparent>
            <View>
              <Text>Yedek Parolası</Text>
            </View>
          </Modal>
        ) : null}
      </View>
    );
    await act(async () => kok.render(<Agac acik={false} />));
    await act(async () => kok.render(<Agac acik />));
    const ges = document.querySelector('[aria-label="Acil durdur"]');
    const modal = Array.from(document.querySelectorAll("div")).reverse().find((d) => d.textContent === "Yedek Parolası");
    const g = etkinKatman(ges!);
    const m = etkinKatman(modal!);
    expect(m[1]).toBeGreaterThan(g[1]); // aparat: Modal kabı body'de GES'ten SONRA
    expect(ustte(g, m)).toBe(true);
  });
});
