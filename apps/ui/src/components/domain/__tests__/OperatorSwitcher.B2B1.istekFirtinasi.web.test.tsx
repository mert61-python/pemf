/**
 * @jest-environment jsdom
 */
// Author: mertaygn, cglrgrkn
/**
 * 2-B yeni bulgu B2B-1 — operatör penceresi AÇIKKEN `/operators` İSTEK FIRTINASI.
 * =============================================================================
 * ÖLÇÜLEN KUSUR (2-B, D2.E13 kapısı kurulurken): `OperatorSwitcher` listeyi `useEffect(() => { if (acik) ctx.refresh() },
 * [acik, ctx])` ile yeniliyordu. `refresh` her çağrıda YENİ bir dizi kurar → bağlam değeri değişir → effect yeniden koşar →
 * yeniden `refresh` … Pencere açık kaldıkça döngü ağ gecikmesiyle sınırlı sürer: act DIŞI, 5 ms ağ gecikmesiyle 1 sn'de
 * **30** `GET /operators` (kapatınca 0). Anında dönen yanıtla mikro-görev kuyruğu hiç boşalmaz (sayfa donar).
 *
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher, apiClient; sahte yalnız `fetch` (5 ms gecikme) ve Supabase
 * istemcisi. Üretim zamanlaması için `act` KULLANILMAZ (act kapsamı render'ları kapsam bitene dek bekletir → döngü
 * görünmez; ölçüldü: act içinde 1).
 * ⚠️ MUTASYON: effect bağımlılığını yeniden `[acik, ctx]` yapmak → KIRMIZI.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("../../../context/__tests__/operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { AuthProvider } from "@/context/AuthContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { cipEtiketi, sahteSunucu } from "../../../context/__tests__/operatorAparati";

const bekle = (ms: number) => new Promise((r) => setTimeout(r, ms));
let kok: Root;
let eskiAct: unknown;

beforeEach(() => {
  eskiAct = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT;
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
});
afterEach(async () => {
  kok?.unmount();
  await bekle(20);
  document.body.innerHTML = "";
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: unknown }).IS_REACT_ACT_ENVIRONMENT = eskiAct;
});

it("KRİTİK: operatör penceresi açıkken liste YALNIZ açılışta yenilenir (istek fırtınası yok)", async () => {
  const { fetchSahte, kayit } = sahteSunucu([{ email: "dr.a@klinik.com", display_name: "Dr. A" }]);
  global.fetch = (async (...a: unknown[]) => {
    await bekle(5); // gerçek ağ gecikmesi (loopback + backend)
    return (fetchSahte as unknown as (...x: unknown[]) => unknown)(...a);
  }) as unknown as typeof fetch;
  const kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
  kok.render(
    <AuthProvider>
      <OperatorProvider>
        <OperatorSwitcher />
      </OperatorProvider>
    </AuthProvider>,
  );
  await bekle(500);
  const operatorler = () => kayit.filter((k) => k.yol === "/operators").length;
  const once = operatorler();
  (document.querySelector(`[aria-label="${cipEtiketi()}"]`) as HTMLElement).click();
  await bekle(1000);
  const acikken = operatorler() - once;
  expect(document.body.textContent).toContain("Dr. A"); // pencere açık ve liste yüklendi
  expect(acikken).toBeGreaterThanOrEqual(1); // açılışta bir kez yenilenir
  expect(acikken).toBeLessThanOrEqual(2); // fırtına yok (HEAD: ~30)
});
