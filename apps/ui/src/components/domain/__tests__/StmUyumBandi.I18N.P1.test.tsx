// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · KRİTİK — kart ↔ uygulama uyum bandı: bilinen kod (FW-PAKET / FW-KIMLIK) için metin arayüz kataloğundan SEÇİLİ dilde gelir;
 * sunucu `mesaj`ı Türkçe VERİ olarak gelse de İngilizcede Türkçe görünmez. Bilinmeyen kod / eski sunucu → sunucu metni (davranış aynı).
 */
let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import React from "react";
import { act, render } from "@testing-library/react-native";

import { StmUyumBandi, stmUyumBandiMetni } from "@/components/domain/StmUyumBandi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const K1_TR = "Cihaz kartının yazılımı bu uygulama sürümüyle uyumsuz — bobinler çalışmaz. Teknik desteği arayın (kod: FW-PAKET).";
const K1_EN = "The device board's firmware is incompatible with this app version — the coils will not run. Call technical support (code: FW-PAKET).";
const K2_TR = "Cihaz kartı doğrulanamadı. Kartın üzerindeki SİYAH sıfırlama düğmesine bir kez basın (mavi değil).";

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

describe("KRİTİK: STM uyum bandı seçili dilde", () => {
  it("Türkçe: sunucu mesajıyla bayt bayt aynı metin", () => {
    mockSnapshot = { stm: "online", stmUyum: { uyumlu: false, kod: "FW-PAKET", mesaj: K1_TR, ayrinti: "a" } };
    expect(stmUyumBandiMetni(mockSnapshot.stmUyum as never)?.mesaj).toBe(K1_TR);
    const u = render(<StmUyumBandi />);
    expect(u.getByText(K1_TR)).toBeTruthy();
  });

  it("İngilizce (bayrak açık): bilinen kodda İngilizce metin, sunucu Türkçesi GÖRÜNMEZ; kod yoksa / bilinmiyorsa sunucu metni", async () => {
    __bayrakTestiAyarla(true);
    await act(async () => {
      await dilSec("en", depo);
    });
    mockSnapshot = { stm: "online", stmUyum: { uyumlu: false, kod: "FW-PAKET", mesaj: K1_TR, ayrinti: "a" } };
    const u = render(<StmUyumBandi />);
    expect(u.getByText(K1_EN)).toBeTruthy();
    expect(u.queryByText(K1_TR)).toBeNull();
    mockSnapshot = { stm: "online", stmUyum: { uyumlu: null, kod: "FW-KIMLIK", mesaj: K2_TR, ayrinti: "x" } };
    const sari = stmUyumBandiMetni(mockSnapshot.stmUyum as never);
    expect(sari?.tur).toBe("sari");
    expect(sari?.mesaj).toContain("BLACK reset button");
    // bilinmeyen kod → sunucu metni aynen (davranış değişmedi)
    expect(stmUyumBandiMetni({ uyumlu: false, kod: "FW-BILINMEYEN", mesaj: "Sunucu metni", ayrinti: "" } as never)?.mesaj).toBe("Sunucu metni");
  });
});
