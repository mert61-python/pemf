// Author: mertaygn, cglrgrkn
/**
 * CH1 · Y151 — "E-posta hesapları" menüsü (`HesapMenusu`).
 * ========================================================
 * SÖZLEŞME:
 *  · açık hesaplar listelenir, etkin işaretli ("Etkin"); diğerine tek dokunuşla geçilir;
 *  · çok kullanıcılı cihazda geçişten ÖNCE seçili hekim KİLİTLENİR (hesap geçişi hekim kilidini atlatmaz);
 *  · SEANS SÜRERKEN geçiş, "Hesap ekle" ve ETKİN hesaptan çıkış KAPALI + neden yazılı; park edilmiş hesaptan çıkış açık;
 *  · metin hesabı (e-posta) hekimden (PIN, "Hekim Değiştir (bu cihaz)") AYIRIR;
 *  · pencere açıkken de ACİL DURDUR erişilebilir (Modal kabuğun kayan düğmesini örttüğü için kendi düğmesini çizer);
 *  · >1 hesapta "Tüm hesaplardan çık" etiketi gerçeği söyler ve kabuğun teardown korumalı çıkışını çağırır.
 */
let mockAuth: any;
let mockSnap: any;
let mockOp: any;
const mockConfirm = jest.fn(async () => true);
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockAuth }));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap, donanimBelirsiz: false }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => mockOp }));
jest.mock("@/services/apiClient", () => ({ platformConfirm: (...a: unknown[]) => (mockConfirm as any)(...a) }));
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: {} },
  oturumDeposu: { getItem: async () => null, setItem: async () => undefined, removeItem: async () => undefined },
}));
jest.mock("@/components/ui/GlobalEmergencyStop", () => {
  const { Text } = require("react-native");
  const R = require("react");
  return { GlobalEmergencyStop: () => R.createElement(Text, null, "ACIL-DURDUR") };
});

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { HesapMenusu } from "@/components/domain/HesapMenusu";
import { hesapGecisSeansEngeli } from "@/services/hesapGecisi";

const sira: string[] = [];
const BOSTA = { coils: [{ id: 1, running: false }], activeTreatment: { isActive: false } };
const SEANSTA = { coils: [{ id: 1, running: true }], activeTreatment: { isActive: true } };

beforeEach(() => {
  sira.length = 0;
  mockConfirm.mockClear();
  mockSnap = BOSTA;
  mockOp = { multiUser: true, active: { email: "dr.x@klinik.com" }, lock: jest.fn(() => sira.push("lock")) };
  mockAuth = {
    session: { email: "a@klinik.com" },
    hesaplar: ["a@klinik.com", "b@klinik.com"],
    hesabaGec: jest.fn(async () => { sira.push("gec"); return { ok: true }; }),
    hesaptanCik: jest.fn(async () => ({ ok: true })),
    hesapEkle: jest.fn(async () => { sira.push("ekle"); }),
  };
});

const ciz = (onTumundenCik = jest.fn()) => ({
  u: render(<HesapMenusu visible onClose={jest.fn()} onTumundenCik={onTumundenCik} />),
  onTumundenCik,
});
const pasif = (el: any) => el.props.accessibilityState?.disabled === true || el.props["aria-disabled"] === true;

it("KRİTİK: açık hesaplar listelenir, etkin işaretli; diğerine geçişte ÖNCE hekim kilitlenir, SONRA geçilir", async () => {
  const { u } = ciz();
  expect(u.getByLabelText("a@klinik.com — etkin hesap")).toBeTruthy();
  expect(u.getByText("Etkin")).toBeTruthy();
  await act(async () => { fireEvent.press(u.getByLabelText("b@klinik.com hesabına geç")); });
  expect(mockAuth.hesabaGec).toHaveBeenCalledWith("b@klinik.com");
  expect(sira).toEqual(["lock", "gec"]);
});

it("KRİTİK seans sürerken: geçiş / hesap ekle / ETKİN hesaptan çıkış KAPALI + neden; park edilmiş hesaptan çıkış AÇIK", async () => {
  mockSnap = SEANSTA;
  const { u } = ciz();
  expect(u.getByTestId("hesap-menusu-engel").props.children).toBe(hesapGecisSeansEngeli());
  const gec = u.getByLabelText("b@klinik.com hesabına geç");
  expect(pasif(gec)).toBe(true);
  await act(async () => { fireEvent.press(gec); });
  expect(mockAuth.hesabaGec).not.toHaveBeenCalled();
  await act(async () => { fireEvent.press(u.getByLabelText("Hesap ekle")); });
  expect(mockAuth.hesapEkle).not.toHaveBeenCalled();
  expect(pasif(u.getByLabelText("a@klinik.com hesabından çık"))).toBe(true);
  await act(async () => { fireEvent.press(u.getByLabelText("a@klinik.com hesabından çık")); });
  expect(mockAuth.hesaptanCik).not.toHaveBeenCalled();
  await act(async () => { fireEvent.press(u.getByLabelText("b@klinik.com hesabından çık")); });
  expect(mockAuth.hesaptanCik).toHaveBeenCalledWith("b@klinik.com");
});

it("KRİTİK 'Hesap ekle' (boşta): ÖNCE hekim kilitlenir, sonra ekleme kipi açılır", async () => {
  const { u } = ciz();
  await act(async () => { fireEvent.press(u.getByLabelText("Hesap ekle")); });
  expect(sira).toEqual(["lock", "ekle"]);
});

it("metin hesap (e-posta) ile hekimi (PIN) AYIRIR; pencere açıkken ACİL DURDUR erişilebilir", () => {
  const { u } = ciz();
  const aciklama = u.getByTestId("hesap-menusu-aciklama").props.children as string;
  expect(aciklama).toContain("Hesap = giriş yaptığınız e-posta");
  expect(aciklama).toContain("Hekim Değiştir (bu cihaz)");
  expect(u.getByText("ACIL-DURDUR")).toBeTruthy();
});

it("KRİTİK >1 hesapta 'Tüm hesaplardan çık' etiketi gerçeği söyler ve kabuğun çıkışını çağırır; tek hesapta 'Çıkış yap'", async () => {
  const { u, onTumundenCik } = ciz();
  await act(async () => { fireEvent.press(u.getByLabelText("Tüm hesaplardan çık")); });
  expect(onTumundenCik).toHaveBeenCalledTimes(1);
  mockAuth = { ...mockAuth, hesaplar: ["a@klinik.com"] };
  const tek = render(<HesapMenusu visible onClose={jest.fn()} onTumundenCik={jest.fn()} />);
  expect(tek.queryByLabelText("Tüm hesaplardan çık")).toBeNull();
  expect(tek.getByLabelText("Çıkış yap")).toBeTruthy();
});

it("KARŞIT tek kullanıcılı cihaz (kayıtlı hekim yok): geçişte kilitlenecek hekim yok, geçiş yine yapılır", async () => {
  mockOp = { multiUser: false, active: null, lock: jest.fn() };
  const { u } = ciz();
  await act(async () => { fireEvent.press(u.getByLabelText("b@klinik.com hesabına geç")); });
  expect(mockOp.lock).not.toHaveBeenCalled();
  expect(mockAuth.hesabaGec).toHaveBeenCalledWith("b@klinik.com");
});
