// Author: mertaygn, cglrgrkn
/**
 * DONANIM-CALISIYOR OLCUSU TEK KAYNAK (denetim bulgusu M4, 2026-08-23).
 *
 * OLCULEN DURUM: iki guncelleme bandi da (MobileUpdateBanner, SurumFarkiBanner) gizlenme kapisi
 * olarak YALNIZ `activeTreatment.isActive`e bakiyordu. Ama bobinler SEANSSIZ da calisir (AI Pro,
 * bobin paneli, baska istemci) — o durumda `isActive` false kalir. Deponun geri kalani ZATEN daha
 * genis olcuyu kullaniyor:
 *   · GlobalEmergencyStop.tsx:35  `(snapshot.coils ?? []).filter(c => c?.running).length`
 *   · useTeardownGuard.ts:56      ayni ifade
 *   · useApkGuncelleme.ts:61      `s?.is_active === true || s?.hardware_running === true`
 * Yani kapi 2. tur denetiminden sonra kancayla birlikte guncellenmemis, geride kalan katmandi.
 *
 * SOZLESME: tek kaynak `useDonanimCalisiyor()`. Bobin hastanin uzerinde ENERJILI iken hicbir
 * yonetimsel bant/dugme cizilmez — "seans kaydi acik mi" degil, "donanim suruyor mu" sorulur.
 *
 * ⚠️ Bu bir GORUNURLUK kapisidir, guvenlik limiti DEGILDIR: acil durdurma yolunu hicbir kosulda
 * etkilemez (GlobalEmergencyStop tam tersine bobin calisirken GORUNUR).
 */
import React from "react";
import { render } from "@testing-library/react-native";
import { Text } from "react-native";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));

import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";

function Sonda() {
  return <Text>{useDonanimCalisiyor() ? "CALISIYOR" : "BOSTA"}</Text>;
}

function olc(snapshot: Record<string, unknown>) {
  mockSnapshot = snapshot;
  return render(<Sonda />).toJSON();
}

it("KRITIK: SEANSSIZ calisan bobin 'calisiyor' sayilir (bandin sizdigi durum)", () => {
  const j = JSON.stringify(
    olc({ activeTreatment: { isActive: false }, coils: [{ id: 6, running: false }, { id: 7, running: true }] }),
  );
  expect(j).toContain("CALISIYOR");
});

it("KRITIK: aktif seans 'calisiyor' sayilir (eski davranis korunur)", () => {
  const j = JSON.stringify(olc({ activeTreatment: { isActive: true }, coils: [] }));
  expect(j).toContain("CALISIYOR");
});

it("KARSIT-KANIT: hicbiri yokken BOSTA — kapi asiri genislemesin (bant hic cikmaz olurdu)", () => {
  const j = JSON.stringify(
    olc({ activeTreatment: { isActive: false }, coils: [{ id: 1, running: false }] }),
  );
  expect(j).toContain("BOSTA");
});

it("KARSIT-KANIT: veri hic yokken BOSTA (bilinmiyor = bant gosterilebilir, susturma degil)", () => {
  expect(JSON.stringify(olc({}))).toContain("BOSTA");
});
