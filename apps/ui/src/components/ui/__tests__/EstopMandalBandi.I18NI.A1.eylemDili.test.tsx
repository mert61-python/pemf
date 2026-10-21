// Author: mertaygn, cglrgrkn
/**
 * I18NI-A1.1 — ACİL DURDURMA MANDALI bandı İngilizcede Türkçe EYLEM cümlesi basmamalı.
 *
 * Sunucu (`api_server._stm_red_aktif_seansi_durdur`) kart duty reddinde / kart uyumsuzluğunda mandal `eylem`ini Türkçe SABİT bırakır
 * (WS yükü dil bilmez; TR bant bayt bayt aynı). Düzeltilmiş sunucu ek alan `eylemler = {tr, en}` taşır; bant etkin dildekini seçmeli.
 * Yük AŞAĞIDA gerçek sunucu çıktısıdır (tests/test_i18ni_mandal_eylemi_iki_dilli.py ile aynı NACK: bobin 1, %80 > %50, bipolar).
 * Bugün KIRMIZI (bant `eylemler`i okumaz → İngilizce bant ortasında Türkçe cümle); ürün düzelince YEŞİL. TR görünüm göç öncesiyle AYNI.
 */
let mockSnapshot: Record<string, unknown> = { coils: [], activeTreatment: { isActive: false } };
jest.mock("@/services/apiClient", () => ({ apiPost: jest.fn(), platformConfirm: jest.fn(), platformAlert: jest.fn() }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnapshot }) }));

import React from "react";
import { act, render } from "@testing-library/react-native";
import { EstopMandalBandi } from "@/components/ui/EstopMandalBandi";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/;
// Sunucunun bugünkü `eylem` metni (dil="tr", sifirla=True) — göç öncesi f-string çıktısıyla bayt bayt aynı.
const EYLEM_TR =
  "Bobin 1 çift yönlü kipte en fazla %50 çalışabilir; %80 kabul edilmedi. Duty'yi %50 veya altına indirin (ya da ⚡ Sürüş Kipi'nden bu bobini Unipolar yapın), sonra 'Sıfırla'ya basın ve yeniden başlatın.";
const EYLEM_EN =
  "Coil 1 can run at most 50% in two-way mode; 80% was not accepted. Lower the duty to 50% or below (or set this coil to Unipolar in ⚡ Drive Mode), then press 'Reset' and start again.";
const yuk = (m: Record<string, unknown>) => ({
  coils: [],
  activeTreatment: { isActive: false },
  estopMandali: { aktif: true, neden: "stm_komut_reddi", eylem: EYLEM_TR, eylemSifirlaSoyler: true, ...m },
});
const bantMetni = (u: ReturnType<typeof render>) =>
  u.getAllByText(/./).map((n) => String(n.props.children)).join(" | ");

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("TR: bant göç öncesiyle AYNI (eylem Türkçe, ikinci 'Sıfırla' cümlesi yok)", () => {
  mockSnapshot = yuk({ eylemler: { tr: EYLEM_TR, en: EYLEM_EN } });
  const u = render(<EstopMandalBandi />);
  expect(
    u.getByText(`Neden: kart komutları reddetti. ${EYLEM_TR} Bobinlerin durduğunu cihazda kontrol edin. Sıfırlama bobinleri başlatmaz.`),
  ).toBeTruthy();
});

it("EN: duty reddi mandal bandında Türkçe harf YOK (eylem etkin dilde)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  mockSnapshot = yuk({ eylemler: { tr: EYLEM_TR, en: EYLEM_EN } });
  const u = render(<EstopMandalBandi />);
  const metin = bantMetni(u);
  expect(metin).toContain("EMERGENCY STOP LATCHED");
  expect(metin).not.toMatch(TR_HARF);
  expect(metin).toContain(EYLEM_EN);
});

it("eski sunucu (eylemler YOK): bant eylem metnini aynen basar (geri uyum)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  mockSnapshot = yuk({});
  const u = render(<EstopMandalBandi />);
  expect(bantMetni(u)).toContain(EYLEM_TR);
});
