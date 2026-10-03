// Author: mertaygn, cglrgrkn
/**
 * Y46 (sahip) — açılışta mandal önceki oturumdan KURULUYSA bant nedeniyle gösterilir: "önceki oturumda ACİL DURDUR —
 * sıfırlanmadı". Backend diskten yüklenen mandalın nedenini `onceki_oturum:<asıl neden>` ve `oncekiOturum: true` olarak
 * verir (`utils/estop_mandali.kalicilik_kur`; Python kapısı `test_Y46_…`). Bozuk dosya: `onceki_oturum:dosya_okunamadi`.
 * Y45: seanssız kopma / watchdog nedenleri de operatör diliyle okunur.
 * ⚠️ MUTASYON: `mandalNedeni`'nin önceki-oturum dalı silinirse bant iç adı gizleyip genel "acil durdurma" der → KIRMIZI.
 */
import React from "react";
import { render } from "@testing-library/react-native";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import { EstopMandalBandi, mandalNedeni } from "@/components/ui/EstopMandalBandi";

const bant = (neden: string, oncekiOturum = true) => {
  mockSnapshot = { coils: [], activeTreatment: { isActive: false }, estopMandali: { aktif: true, neden, oncekiOturum } };
  return render(<EstopMandalBandi />);
};

describe("Y46 — önceki oturumdan kalan mandalın bandı", () => {
  it("KRİTİK: diskten yüklenen mandal 'önceki oturumda ACİL DURDUR — sıfırlanmadı' der ve asıl nedeni korur", () => {
    const u = bant("onceki_oturum:manual");
    expect(u.queryByText(/önceki oturumda ACİL DURDUR — sıfırlanmadı/)).not.toBeNull();
    expect(u.queryByText(/ACİL DURDUR düğmesi/)).not.toBeNull();
  });

  it("KRİTİK: okunamayan mandal dosyası açıkça söylenir (güvenli taraf: mandal kurulu)", () => {
    const u = bant("onceki_oturum:dosya_okunamadi");
    expect(u.queryByText(/önceki oturumda ACİL DURDUR — sıfırlanmadı/)).not.toBeNull();
    expect(u.queryByText(/mandal dosyası okunamadı/)).not.toBeNull();
  });

  it("KARŞIT: bu oturumdaki mandal 'önceki oturum' DEMEZ", () => {
    const u = bant("manual", false);
    expect(u.queryByText(/önceki oturumda/)).toBeNull();
    expect(mandalNedeni("stm_watchdog_timeout")).toBe("STM32 watchdog zaman aşımı");
  });
});
