/**
 * @jest-environment jsdom
 */
/**
 * SG.G7 (sahip gözlemi 2026-10-13, telefonda APK 2.3.34) — "Kullanıcı Değiştir" penceresi.
 * Sahip: "geçiş yap butonuna basılmıyor ne işe yarıyor bu buton mailler arası geçiş yapmıyor mu" + "bu cihaza kaydol … bu ne işe yarıyor".
 * Ölçülen durum (`ec5e967c`): başlık "Kullanıcı Değiştir" (e-posta HESABI değişiyor sanılıyor); "Geçiş Yap" `disabled` ama stil
 * pasifliği GÖSTERMİYOR ve neden basılmadığı söylenmiyor; liste boşken "Bu cihazda kayıtlı operatör yok."; "Bu cihaza kaydol" amacını /
 * sonucunu söylemiyor; ad alanı PIN'in harf aralıklı stilini taşıyor; Ev Sahibi'nde de çok-hekimli klinik penceresi.
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher, apiClient. Sahte yalnız `fetch` (sahteSunucu) ve Supabase istemcisi.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("../../../context/__tests__/operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import { AuthProvider } from "@/context/AuthContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { Sahne, cipEtiketi, sahteSunucu, type SahteOperator } from "../../../context/__tests__/operatorAparati";

let s: Sahne;
beforeEach(() => { s = new Sahne(); });
afterEach(async () => { await s.sok(); });

async function ac(operatorler: SahteOperator[], props: React.ComponentProps<typeof OperatorSwitcher> = {}) {
  const { fetchSahte } = sahteSunucu(operatorler);
  global.fetch = fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <OperatorProvider>
        <OperatorSwitcher {...props} />
      </OperatorProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
  // Ev Sahibi + tek kullanıcı: çip oturum e-postasını gösterir ("Operatör seç" etiketi).
  await s.tikla(cipEtiketi());
  await s.bosalt(10);
}

const metin = (id: string) => (document.querySelector(`[data-testid="${id}"]`)?.textContent || "").replace(/\s+/g, " ").trim();

test("KRİTİK: başlık ne yaptığını söyler (bu cihazdaki hekimler arası geçiş) ve e-posta hesabının nasıl değişeceğini söyler", async () => {
  await ac([{ email: "dr.a@klinik.com", display_name: "Dr A" }], { kip: "veterinarian" });
  expect(s.metin()).toContain("Hekim Değiştir (bu cihaz)");
  expect(s.metin()).not.toContain("Kullanıcı Değiştir");
  expect(metin("operator-aciklama")).toBe(
    "Bu cihazı ortak kullanan hekimler arasında PIN ile hızlı geçiş. E-posta hesabını değiştirmek için çıkış yapıp diğer hesapla giriş yapın.",
  );
});

test("KRİTİK: liste BOŞKEN 'Geçiş yap' görünür biçimde PASİF ve NEDENİ söylenir", async () => {
  await ac([], { kip: "veterinarian" });
  const d = s.etiket("Geçiş yap");
  expect(d.getAttribute("aria-disabled")).toBe("true");
  expect(window.getComputedStyle(d).opacity).toBe("0.6");
  expect(metin("operator-pasif-nedeni")).toBe('Bu cihazda kayıtlı hekim yok — önce "Bu cihaza kaydol".');
  expect(s.metin()).toContain("Bu cihazda kayıtlı hekim yok.");
});

test("KRİTİK: seçim / PIN eksikken neden söylenir; PIN tamamlanınca düğme ETKİN olur (karşıt)", async () => {
  await ac([{ email: "dr.a@klinik.com", display_name: "Dr A" }], { kip: "veterinarian" });
  expect(metin("operator-pasif-nedeni")).toBe("Listeden hekim seçin ve 6 haneli PIN'i girin.");
  await s.tikla("Seç: Dr A");
  expect(metin("operator-pasif-nedeni")).toBe("6 haneli PIN'i girin.");
  await s.yaz("PIN", "123456");
  expect(document.querySelector('[data-testid="operator-pasif-nedeni"]')).toBeNull();
  const d = s.etiket("Geçiş yap");
  expect(d.getAttribute("aria-disabled")).not.toBe("true");
  expect(window.getComputedStyle(d).opacity).not.toBe("0.6");
});

test("KRİTİK: 'Başka hesapla giriş yap' MEVCUT çıkış akışını çağırır (yeni akış yok)", async () => {
  const cikis = jest.fn();
  await ac([{ email: "dr.a@klinik.com", display_name: "Dr A" }], { kip: "veterinarian", onBaskaHesap: cikis });
  await s.tikla("Başka hesapla giriş yap");
  expect(cikis).toHaveBeenCalledTimes(1);
});

test("KRİTİK: 'Bu cihaza kaydol' amacını ve SONUCUNU söyler; ad alanı harf aralıklı DEĞİL (PIN alanı aynen)", async () => {
  await ac([], { kip: "veterinarian" });
  await s.tikla("Bu cihaza kaydol");
  const a = metin("operator-aciklama");
  expect(a).toContain("Bu cihazı başka hekimlerle ortak kullanıyorsanız kaydolun: hasta, seans ve AI kayıtları adınıza işlenir");
  expect(a).toContain("kayıt yazan işlemler seçili hekim ister, hekim seçilmeden listeler kayıt göstermez ve 10 dk hareketsizlikte seçim düşer (seans sürerken düşmez)");
  const ad = s.etiket("Görünen ad");
  const pin = s.etiket("PIN");
  expect(["", "normal", "0px"]).toContain(window.getComputedStyle(ad).letterSpacing);
  expect(["", "normal", "0px"]).not.toContain(window.getComputedStyle(pin).letterSpacing);
  expect(metin("operator-pasif-nedeni")).toBe("Görünen adınızı yazın ve 6 haneli PIN belirleyin.");
});

test("KRİTİK: araştırma profilinde terim 'araştırmacı' (hekim DEĞİL — karar #12)", async () => {
  await ac([], { kip: "researcher" });
  expect(s.metin()).toContain("Araştırmacı Değiştir (bu cihaz)");
  await s.tikla("Bu cihaza kaydol");
  expect(metin("operator-aciklama")).toContain("başka araştırmacılarla ortak kullanıyorsanız");
});

test("KRİTİK: Ev Sahibi + tek kullanıcılı cihaz → yalnız hesap penceresi (hekim listesi / PIN / kaydol YOK)", async () => {
  const cikis = jest.fn();
  await ac([], { kip: "pet_owner", onBaskaHesap: cikis });
  expect(s.metin()).toContain("Hesap");
  expect(metin("operator-aciklama")).toBe(
    "Giriş yapılan hesap: dr.a@klinik.com. Başka bir e-posta hesabına geçmek için çıkış yapıp o hesapla giriş yapın.",
  );
  expect(s.varMi("Geçiş yap")).toBe(false);
  expect(s.varMi("Bu cihaza kaydol")).toBe(false);
  await s.tikla("Başka hesapla giriş yap");
  expect(cikis).toHaveBeenCalledTimes(1);
});

test("KARŞIT: Ev Sahibi ama cihaz ÇOK KULLANICILI (kayıtlı operatör var) → tam pencere kalır (yazma yolları seçili kişi ister)", async () => {
  await ac([{ email: "dr.a@klinik.com", display_name: "Dr A" }], { kip: "pet_owner" });
  expect(s.metin()).toContain("Kişi Değiştir (bu cihaz)");
  expect(s.varMi("Seç: Dr A")).toBe(true);
});
