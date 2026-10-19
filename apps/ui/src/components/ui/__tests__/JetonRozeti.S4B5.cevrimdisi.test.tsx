// Author: mertaygn, cglrgrkn
/**
 * S-4B.5 (sahip kararı 2026-10-19) — ücretlendirme açıkken internetsiz yapay zekâ analizi YAPILMAZ (servers/jeton.py: 402
 * `cevrimdisi`). Rozet "—" iken dokununca çıkan açıklama eskiden "Analiz yapmaya devam edebilirsiniz; kullanım internet gelince
 * uzlaşır" diyordu → kullanıcı analizi dener, 402 alır. GERÇEK bileşen + GERÇEK `bilinmeyenBakiyeAciklamasi`; sahte yalnız bakiye
 * okuması (`apiGet`) ve toast köprüsü.
 * ⚠️ MUTASYON: bileşen eski satır içi metne dönerse ya da açıklamayı göstermezse KIRMIZI.
 */
import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => ({ etkin: true, bilinmiyor: true, sebep: "cevrimdisi" })),
}));

import { emitToast } from "@/services/toastBridge";
import { JetonRozeti } from "@/components/ui/JetonRozeti";

describe("JetonRozeti — internetsiz '—' açıklaması (S-4B.5)", () => {
  it("KRİTİK: dokununca analiz için internet gerektiğini ve tedavinin internetsiz sürdüğünü söyler", async () => {
    const u = render(<JetonRozeti />);
    const rozet = await waitFor(() => u.getByLabelText(/Kalan jeton: —/));
    fireEvent.press(rozet);
    const metin = (emitToast as jest.Mock).mock.calls.map((c) => String(c[0])).join("\n");
    expect(metin).toContain("internet gerekir");
    expect(metin).toContain("acil durdurma");
    expect(metin).not.toMatch(/devam edebilirsiniz|uzlaşır/);
  });
});
