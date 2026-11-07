/**
 * @jest-environment jsdom
 */
/**
 * KP-3 C · OperatorSwitcher kapsanmayan kolları — her test bir DAVRANIŞ iddiası (SG_G7 düzeneğinin aynısı):
 *  - PIN ile geçiş: 401 → "PIN hatalı" ve PIN alanı TEMİZLENİR; 423 → "çok hatalı deneme — kilitli" (kilitliyken "PIN hatalı"
 *    DENMEZ); sunucuya ulaşılamazsa "cihaza ulaşılamadı".
 *  - Bu cihaza kaydol: ad boş ya da PIN 6 hane değilse istek GİTMEZ; e-posta zaten kayıtlıysa (401) PIN DEĞİŞTİRME akışına geçilir —
 *    mevcut PIN alanı (yalnız rakam, 6 hane) açılır, eksikken istek GİTMEZ ve gönderimde `eski_pin` taşınır; 423 → kilitli (mevcut PIN
 *    temizlenir); 400 → "kayıt yapılamadı" (PIN temizlenir); 5xx → "cihaza ulaşılamadı"; başarıda pencere kapanır. "Listeye dön" kayıt
 *    kipini ve PIN değiştirme durumunu SIFIRLAR.
 * GERÇEK: AuthProvider, OperatorProvider, OperatorSwitcher, apiClient. SAHTE: fetch (sahteSunucu), Supabase istemcisi.
 */
jest.mock("react-native", () => jest.requireActual("react-native-web"));
jest.mock("@/services/supabaseAuth", () => require("../../../context/__tests__/operatorAparati").supabaseSahte("dr.a@klinik.com"));

import React from "react";
import i18n from "i18next";
import { AuthProvider } from "@/context/AuthContext";
import { OperatorProvider } from "@/context/OperatorContext";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";
import { Sahne, cipEtiketi, sahteSunucu, type Istek } from "../../../context/__tests__/operatorAparati";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
let s: Sahne;
let kayit: Istek[];
let yanit: Record<string, [number, unknown]>;
beforeEach(() => { s = new Sahne(); yanit = {}; });
afterEach(async () => { await s.sok(); });

async function ac() {
  const sunucu = sahteSunucu([{ email: "dr.b@klinik.com", display_name: "Dr B" }], (yol) => yanit[yol]);
  kayit = sunucu.kayit;
  global.fetch = sunucu.fetchSahte as unknown as typeof fetch;
  await s.ciz(
    <AuthProvider>
      <OperatorProvider>
        <OperatorSwitcher kip="veterinarian" />
      </OperatorProvider>
    </AuthProvider>,
  );
  await s.bosalt(10);
  await s.tikla(cipEtiketi());
  await s.bosalt(10);
}
const istekler = (yol: string) => kayit.filter((k) => k.yol === yol);
const pinDegeri = () => (s.etiket(T("hesap.operator.pin")) as HTMLInputElement).value;

describe("PIN ile geçiş", () => {
  it.each([
    [401, "hesap.operator.pinHatali"],
    [423, "hesap.operator.cokHataliKilitli"],
    [500, "hesap.operator.cihazaUlasilamadi"],
  ])("sunucu %s → doğru ileti; PIN alanı temizlenir", async (durum, ileti) => {
    yanit["/operators/verify"] = [durum as number, { detail: "x" }];
    await ac();
    await s.tikla(T("hesap.operator.secEtiketi", { ad: "Dr B" }));
    await s.yaz(T("hesap.operator.pin"), "123456");
    await s.tikla(T("hesap.operator.gecisYapEtiketi"));
    await s.bosalt(10);
    expect(s.metin()).toContain(T(ileti));
    expect(pinDegeri()).toBe("");
  });
});

describe("bu cihaza kaydol", () => {
  async function kayitKipi() {
    await ac();
    await s.tikla(T("hesap.operator.buCihazaKaydol"));
  }
  const kaydol = async () => { await s.tikla(T("hesap.operator.kaydol")); await s.bosalt(10); };

  it("ad boş / PIN eksik → istek GİTMEZ; 401 → PIN değiştirme akışı (mevcut PIN rakam-süzgeçli, eksikken istek yok, eski_pin taşınır)", async () => {
    await kayitKipi();
    await s.yaz(T("hesap.operator.pin"), "123456");
    await kaydol();
    await s.yaz(T("hesap.operator.gorunenAd"), "Dr A");
    await s.yaz(T("hesap.operator.pin"), "123");
    await kaydol();
    expect(istekler("/operators/enroll")).toHaveLength(0);

    yanit["/operators/enroll"] = [401, { detail: "zaten kayıtlı" }];
    await s.yaz(T("hesap.operator.pin"), "654321");
    await kaydol();
    expect(s.metin()).toContain(T("hesap.operator.zatenKayitli"));
    await s.yaz(T("hesap.operator.mevcutPin"), "12a3");
    expect((s.etiket(T("hesap.operator.mevcutPin")) as HTMLInputElement).value).toBe("123");
    await s.tikla(T("hesap.operator.pinDegistirEtiketi"));
    await s.bosalt(6);
    expect(istekler("/operators/enroll")).toHaveLength(1); // eski PIN eksik → yeni istek YOK
    await s.yaz(T("hesap.operator.mevcutPin"), "111111");
    yanit["/operators/enroll"] = [200, { ok: true, operator_token: "JETON-A" }];
    await s.tikla(T("hesap.operator.pinDegistirEtiketi"));
    await s.bosalt(10);
    expect(istekler("/operators/enroll")[1].govde).toEqual({ email: "dr.a@klinik.com", display_name: "Dr A", pin: "654321", eski_pin: "111111" });
    expect(s.varMi(T("hesap.operator.gorunenAd"))).toBe(false); // başarı → pencere kapandı
  });

  it.each([
    [423, "hesap.operator.cokHataliKilitli", "123456"],
    [400, "hesap.operator.kayitYapilamadi", ""],
    [503, "hesap.operator.cihazaUlasilamadi", ""],
  ])("sunucu %s → doğru ileti (PIN alanı: '%s' sonrası)", async (durum, ileti, pinSonra) => {
    yanit["/operators/enroll"] = [durum as number, { detail: "x" }];
    await kayitKipi();
    await s.yaz(T("hesap.operator.gorunenAd"), "Dr A");
    await s.yaz(T("hesap.operator.pin"), "123456");
    await kaydol();
    expect(s.metin()).toContain(T(ileti));
    expect(pinDegeri()).toBe(pinSonra);
  });

  it("'Listeye dön' kayıt kipini ve PIN değiştirme durumunu sıfırlar", async () => {
    yanit["/operators/enroll"] = [401, {}];
    await kayitKipi();
    await s.yaz(T("hesap.operator.gorunenAd"), "Dr A");
    await s.yaz(T("hesap.operator.pin"), "123456");
    await kaydol();
    expect(s.varMi(T("hesap.operator.mevcutPin"))).toBe(true);
    await s.tikla(T("hesap.operator.listeyeDonEtiketi"));
    expect(s.varMi(T("hesap.operator.mevcutPin"))).toBe(false);
    expect(s.metin()).not.toContain(T("hesap.operator.zatenKayitli"));
    await s.tikla(T("hesap.operator.secEtiketi", { ad: "Dr B" }));
    expect(pinDegeri()).toBe(""); // kayıt kipinde yazılan PIN listeye taşınmaz
    await s.tikla(T("hesap.operator.buCihazaKaydol"));
    expect(s.varMi(T("hesap.operator.mevcutPin"))).toBe(false);
  });
});
