/**
 * KP-8 · src/components/ui/JetonRozeti.tsx kalan dallar — GERÇEK bileşen + GERÇEK `bakiyeDurumu` / `bakiyeMetni`; sahte yalnız bakiye
 * okuması (`apiGet`) ve toast köprüsü (S4B5 düzeneği):
 *  - Bakiye BİTTİYSE rozet ve simge KIRMIZI, kutu "bitti" stilinde; dokununca açıklama HATA tonunda.
 *  - Bakiye AZsa (< 5) SARI, kutu "az" stilinde; açıklama bilgi tonunda.
 *  - Sunucu maliyet tablosunu göndermezse açıklama varsayılan maliyetlerle (görüntü 1 · ağır araştırma 3 · AI Pro seansı 5).
 *  - Kullandıkça öde modelinde borç gelmezse "faturalanmamış 0".
 */
import React from "react";
import { StyleSheet, Text } from "react-native";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
const mockBakiye = { deger: {} as Record<string, unknown> };
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => mockBakiye.deger),
}));

import { emitToast } from "@/services/toastBridge";
import { JetonRozeti } from "@/components/ui/JetonRozeti";
import { colors } from "@/theme/tokens";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);

async function ciz(bakiye: Record<string, unknown>) {
  mockBakiye.deger = bakiye;
  (emitToast as jest.Mock).mockClear();
  const u = render(<JetonRozeti />);
  const rozet = await waitFor(() => u.getByRole("button"));
  return { u, rozet };
}

beforeEach(async () => {
  await act(async () => { await i18n.changeLanguage("tr"); });
});

it("bakiye BİTTİ: kırmızı metin + 'bitti' kutusu; açıklama HATA tonunda", async () => {
  const { u, rozet } = await ciz({ etkin: true, kalan: 0, maliyet: { goruntu: 1, agir_arastirma: 3, ai_pro_seans: 5 } });
  const metin = u.UNSAFE_getAllByType(Text).find((x) => x.props.numberOfLines === 1)!;
  expect(StyleSheet.flatten(metin.props.style).color).toBe(colors.danger);
  fireEvent.press(rozet);
  expect((emitToast as jest.Mock).mock.calls[0][1]).toBe("error");
  u.unmount();
});

it("bakiye AZ: sarı metin; açıklama bilgi tonunda; maliyet tablosu yoksa varsayılan maliyetler (1 · 3 · 5)", async () => {
  const { u, rozet } = await ciz({ etkin: true, kalan: 3 });
  const metin = u.UNSAFE_getAllByType(Text).find((x) => x.props.numberOfLines === 1)!;
  expect(StyleSheet.flatten(metin.props.style).color).toBe(colors.warning);
  fireEvent.press(rozet);
  const [ileti, ton] = (emitToast as jest.Mock).mock.calls[0];
  expect(ton).toBe("info");
  expect(ileti).toBe(T("ana.jeton.aciklama", { kalan: 3, goruntu: 1, arastirma: 3, otonom: 5 }));
  u.unmount();
});

it("kullandıkça öde: borç gelmezse açıklama 'faturalanmamış 0'", async () => {
  const { u, rozet } = await ciz({ etkin: true, odemeModeli: "kullandikca", borcTavani: 100 });
  fireEvent.press(rozet);
  expect((emitToast as jest.Mock).mock.calls[0][0]).toBe(T("ana.jeton.faturalanmamis", { count: 0 }));
  u.unmount();
});
