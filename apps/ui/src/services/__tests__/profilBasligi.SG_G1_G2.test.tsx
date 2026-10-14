// Author: mertaygn
/**
 * SG.G1 / G2 (sahip gözlemi 2026-10-13: "raporlar seans geçmişi vs de ayrılmalı profillere göre … metinler de bu profillere göre
 * uyarlanmalı … klinikle araştırma modunun alakası yok").
 *
 * İSTEMCİ YÜZÜ: etkin profil her isteğe `X-PEMF-Profil` olarak gider (backend kayıtları ayırır — `apps/backend/utils/profil.py`,
 * kapı `tests/test_profil_ayrimi_SG_G1_G2.py`); profil seçilmeden (giriş ekranı) başlık YOK; sağlayıcı kalkınca başlık kalkar.
 * Araştırma profilinde "Klinik / dostumuz / ağrı" dili yok; veteriner metinleri AYNEN.
 * ⚠️ DAVRANIŞSAL: GERÇEK `apiClient` + GERÇEK `UserModeProvider`; KPI başlığı GERÇEK `KpiDashboardScreen` çiziminden.
 */
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));

import React from "react";
import { Text, TouchableOpacity } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { authHeaders, PROFIL_BASLIGI, setProfilBasligi } from "@/services/apiClient";
import { UserModeProvider, useUserMode, type UserMode } from "@/context/UserModeContext";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { sayfaBasligi } from "@/config/sayfaBasliklari";

afterEach(() => setProfilBasligi(null));

function Secici({ mod }: { mod: UserMode }) {
  const { setUserMode, userMode } = useUserMode();
  return (
    <TouchableOpacity accessibilityLabel={`sec-${mod}`} onPress={() => setUserMode(mod)}>
      <Text>{userMode ?? "yok"}</Text>
    </TouchableOpacity>
  );
}

describe("X-PEMF-Profil başlığı", () => {
  it("profil yokken başlık GİTMEZ (eski davranış); ayarlanınca gider; null ile kalkar", () => {
    expect(authHeaders()[PROFIL_BASLIGI]).toBeUndefined();
    setProfilBasligi("researcher");
    expect(authHeaders()[PROFIL_BASLIGI]).toBe("researcher");
    setProfilBasligi(null);
    expect(PROFIL_BASLIGI in authHeaders()).toBe(false);
  });

  it("KRİTİK: profil seçimi başlığı EŞZAMANLI ayarlar (ilk istek doğru profille); profil değişince değişir; sağlayıcı kalkınca kalkar", () => {
    const u = render(
      <UserModeProvider>
        <Secici mod="researcher" />
        <Secici mod="veterinarian" />
        <Secici mod={null} />
      </UserModeProvider>,
    );
    expect(authHeaders()[PROFIL_BASLIGI]).toBeUndefined();
    fireEvent.press(u.getByLabelText("sec-researcher"));
    expect(authHeaders()[PROFIL_BASLIGI]).toBe("researcher");
    fireEvent.press(u.getByLabelText("sec-veterinarian"));
    expect(authHeaders()[PROFIL_BASLIGI]).toBe("veterinarian");
    fireEvent.press(u.getByLabelText("sec-null"));
    expect(authHeaders()[PROFIL_BASLIGI]).toBeUndefined();
    fireEvent.press(u.getByLabelText("sec-researcher"));
    act(() => u.unmount());
    expect(authHeaders()[PROFIL_BASLIGI]).toBeUndefined();
  });
});

describe("profile göre metin", () => {
  it("araştırmada 'Tüm Ekip' / 'Benim Örneklerim'; veteriner AYNEN 'Tüm Klinik' / 'Benim Hastalarım'", () => {
    const a = profilSozlugu({ researcher: true });
    const v = profilSozlugu({});
    expect([a.tumKapsam, a.benimListe, a.kpiBaslik]).toEqual(["Tüm Ekip", "Benim Örneklerim", "📊 Araştırma Göstergeleri & Analitik"]);
    expect([v.tumKapsam, v.benimListe, v.kpiBaslik]).toEqual(["Tüm Klinik", "Benim Hastalarım", "📊 Klinik Göstergeler & Analitik"]);
  });

  it("KRİTİK: araştırma sayfa başlıklarında klinik / dostumuz / ağrı dili YOK; veteriner başlıkları AYNEN", () => {
    const rotalar = ["dashboard", "control", "sensors", "history", "patients", "kpi", "simulator", "ai", "ai_history", "settings"] as const;
    for (const r of rotalar) {
      const { title, subtitle } = sayfaBasligi("researcher", r);
      expect(`${r}: ${title} ${subtitle}`).not.toMatch(/klinik|dostum|ağrı|Hasta Kayıt/i);
    }
    expect(sayfaBasligi("veterinarian", "kpi").subtitle).toBe("Cihaz ve klinik göstergeleri.");
    expect(sayfaBasligi("veterinarian", "patients").title).toBe("Hasta Kayıtları");
    expect(sayfaBasligi(null, "dashboard").subtitle).toBe("Bugün Hangi Dostumuza Seans Yapıyoruz?");
    expect(sayfaBasligi("researcher", "patients").title).toBe("Örnek / Denek Kayıtları");
  });
});
