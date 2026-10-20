// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · Jeton rozeti, bakiye metinleri ve abonelik / plan etiketleri iki dilde. TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * Kritik: "Seans ve acil durdurma jetondan etkilenmez" / "internetsiz de çalışır" güvencesi iki dilde AYNI anlamı taşır.
 * ⚠️ Beklenen metinler BURADA sabittir. VERİ: bakiye sayısı / maliyet değerleri dilden bağımsız.
 */
import React from "react";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
let mockBakiye: Record<string, unknown> = { etkin: true, bilinmiyor: false, kalan: 42, maliyet: { goruntu: 1, agir_arastirma: 3, ai_pro_seans: 5 } };
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn(async () => mockBakiye) }));

import { emitToast } from "@/services/toastBridge";
import { JetonRozeti } from "@/components/ui/JetonRozeti";
import { abonelikDogrulanamadi, planRozetiMetni, tierEtiketi } from "@/config/entitlement";
import { bakiyeMetni, bilinmeyenBakiyeAciklamasi } from "@/services/jetonBakiye";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
  (emitToast as jest.Mock).mockClear();
});
async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}
const toastlar = () => (emitToast as jest.Mock).mock.calls.map((c) => [String(c[0]), c[1]]);

describe("JetonRozeti", () => {
  beforeEach(() => {
    mockBakiye = { etkin: true, bilinmiyor: false, kalan: 42, maliyet: { goruntu: 1, agir_arastirma: 3, ai_pro_seans: 5 } };
  });

  it("TR: rozet etiketi, birim ve açıklama göç öncesiyle aynı; veri (kalan / maliyet) aynen", async () => {
    const u = render(<JetonRozeti />);
    const rozet = await waitFor(() => u.getByLabelText("Kalan jeton: 42. Ayrıntı için dokunun."));
    expect(u.getByText("jeton")).toBeTruthy();
    fireEvent.press(rozet);
    expect(toastlar()).toEqual([
      ["Kalan analiz hakkı: 42. Görüntü/ses 1 · araştırma 3 · otonom seans 5 jeton. Seans ve acil durdurma jetondan etkilenmez.", "info"],
    ]);
  });

  it("KRİTİK EN: rozet etiketi, birim ve açıklama (acil durdurma güvencesi dahil)", async () => {
    await enYap();
    const u = render(<JetonRozeti />);
    const rozet = await waitFor(() => u.getByLabelText("Remaining credits: 42. Tap for details."));
    expect(u.getByText("credits")).toBeTruthy();
    fireEvent.press(rozet);
    expect(toastlar()).toEqual([
      ["Remaining analysis credits: 42. Image/audio 1 · research 3 · autonomous session 5 credits. Sessions and emergency stop are not affected by credits.", "info"],
    ]);
  });

  it("kullandıkça öde: borç sayacı çoğulu (1 / 5) ve faturalanmamış kullanım iletisi; bilinmeyen bakiye açıklaması", async () => {
    mockBakiye = { etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borc: 1 };
    let u = render(<JetonRozeti />);
    let r = await waitFor(() => u.getByLabelText("Kalan jeton: 1 kullanım. Ayrıntı için dokunun."));
    fireEvent.press(r);
    expect(toastlar().pop()).toEqual(["Faturalanmamış kullanım: 1 analiz.", "info"]);
    u.unmount();
    await enYap();
    u = render(<JetonRozeti />);
    r = await waitFor(() => u.getByLabelText("Remaining credits: 1 use. Tap for details."));
    fireEvent.press(r);
    expect(toastlar().pop()).toEqual(["Unbilled usage: 1 analysis.", "info"]);
    u.unmount();
    mockBakiye = { etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borc: 5 };
    u = render(<JetonRozeti />);
    r = await waitFor(() => u.getByLabelText("Remaining credits: 5 uses. Tap for details."));
    fireEvent.press(r);
    expect(toastlar().pop()).toEqual(["Unbilled usage: 5 analyses.", "info"]);
  });

  it("KRİTİK: bakiye bilinmiyorken açıklama internet / seans / acil durdurma güvencesini iki dilde söyler", async () => {
    mockBakiye = { etkin: true, bilinmiyor: true, sebep: "cevrimdisi" };
    let u = render(<JetonRozeti />);
    fireEvent.press(await waitFor(() => u.getByLabelText("Kalan jeton: —. Ayrıntı için dokunun.")));
    expect(toastlar().pop()).toEqual([
      "Jeton bakiyesi okunamadı (internet yok). Yapay zekâ analizi için internet gerekir; seans, acil durdurma ve sensör izleme internetsiz de çalışır.",
      "info",
    ]);
    u.unmount();
    await enYap();
    u = render(<JetonRozeti />);
    fireEvent.press(await waitFor(() => u.getByLabelText("Remaining credits: —. Tap for details.")));
    expect(toastlar().pop()).toEqual([
      "The credit balance could not be read (no internet). AI analysis requires the internet; sessions, emergency stop and sensor monitoring also work offline.",
      "info",
    ]);
  });
});

describe("bakiye metinleri ve plan etiketleri", () => {
  it("TR + EN: giriş gerekli iletisi, plan rozeti (deneme çoğulu, doğrulanamadı, Başlangıç / Starter; Pro adları aynı)", async () => {
    expect(bilinmeyenBakiyeAciklamasi({ etkin: true, bilinmiyor: true, sebep: "kimlik_yok" })).toBe("Jeton bakiyesi için giriş yapmanız gerekiyor.");
    expect(bakiyeMetni({ etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borc: 7 })).toBe("7 kullanım");
    expect(planRozetiMetni({ trialing: true, trialDaysLeft: 5, tier: "baslangic" })).toBe("Deneme · 5 gün kaldı");
    expect(planRozetiMetni({ trialing: false, trialDaysLeft: 0, tier: "baslangic" })).toBe("Başlangıç");
    expect(planRozetiMetni({ trialing: false, trialDaysLeft: 0, tier: "pro" })).toBe("Pro");
    expect(planRozetiMetni({ trialing: false, trialDaysLeft: 0, tier: "pro_plus" })).toBe("Pro+");
    expect(planRozetiMetni({ dogrulanamadi: true, trialing: false, trialDaysLeft: 0, tier: "baslangic" })).toBe("Abonelik doğrulanamadı (internet yok)");
    expect(abonelikDogrulanamadi()).toBe("Abonelik doğrulanamadı (internet yok)");
    await enYap();
    expect(bilinmeyenBakiyeAciklamasi({ etkin: true, bilinmiyor: true, sebep: "kimlik_yok" })).toBe("You need to sign in to see your credit balance.");
    expect(bakiyeMetni({ etkin: true, bilinmiyor: false, odemeModeli: "kullandikca", borc: 7 })).toBe("7 uses");
    expect(planRozetiMetni({ trialing: true, trialDaysLeft: 5, tier: "baslangic" })).toBe("Trial · 5 days left");
    expect(planRozetiMetni({ trialing: true, trialDaysLeft: 1, tier: "baslangic" })).toBe("Trial · 1 day left");
    expect(planRozetiMetni({ trialing: false, trialDaysLeft: 0, tier: "baslangic" })).toBe("Starter");
    expect(tierEtiketi("pro")).toBe("Pro");
    expect(tierEtiketi("pro_plus")).toBe("Pro+");
    expect(planRozetiMetni({ dogrulanamadi: true, trialing: false, trialDaysLeft: 0, tier: "baslangic" })).toBe("Subscription could not be verified (no internet)");
    expect(bakiyeMetni({ etkin: true, bilinmiyor: false, kalan: 99 })).toBe("99"); // sayı: dilden bağımsız
  });
});
