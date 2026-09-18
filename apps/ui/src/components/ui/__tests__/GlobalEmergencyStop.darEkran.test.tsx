// Author: mertaygn, cglrgrkn
/**
 * ACİL DURDUR — DAR EKRANDA DOKUNMA TABANI  [S1/S3, 2026-09-04 responsive denetimi]
 * ================================================================================
 * NEDEN AYRI DOSYA: stiller modül YÜKLENİRKEN bir kez hesaplanır; varsayılan jest cihazında ölçek
 * 1,1 olduğu için dar telefon hiç ölçülmüyordu. Burada cihaz 320 px'e sabitlenip modül TAZE yüklenir.
 *
 * ÖLÇÜLEN GERÇEK (dürüstlük notu — 2026-09-04, bu dosya yazılırken doğrulandı):
 *  · Ölçek TABANI 0,85'tir → `rs(52)` en dar cihazda bile tam 44 çıkar. Yani BUGÜNKÜ tasarım
 *    boyutunda (52) `Math.max(touch.min, …)` sarmalayıcısı HİÇBİR cihazda devreye girmiyor;
 *    onu silen mutasyon bu testi kırmızıya ÇEVİRMEZ. Bunu iddia etmiyoruz.
 *  · Sarmalayıcı bir REGRESYON KAPISIDIR ve işini boyut değişince yapar: ölçülen mutasyon
 *    `rs(52)` → `rs(46)` (birinin düğmeyi "biraz küçültmesi") tabanla 44'te kalır, tabansız
 *    320 px'te 39 px'e düşer ve BU dosya kırmızıya döner (ölçüldü: 2 vaka kırmızı, "Received: 39").
 * Kilitlenen şey formül değil SONUÇTUR: en dar desteklenen cihazda dokunma hedefi < 44 px olamaz.
 *
 * ⚠️ TEST TUZAĞI: `resetModules` sonrası RTL kullanılamaz (kendi kancalarını kaydeder, React
 * örneği ayrışır). Kanca kaydetmeyen `react-test-renderer` taze kayıttan alınır.
 */
import { cihaziKur } from "@/theme/__tests__/olcek";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));

afterEach(() => {
  jest.resetModules();
  jest.dontMock("react-native");
});

/** Verilen cihazda düğmeyi taze yükleyip düzleştirilmiş stilini döndürür. */
function dugmeStili(width: number, height: number, compact = false): Record<string, number> {
  mockSnapshot = { stm: "online", coils: [{ id: 1, running: true, connected: true }] };
  cihaziKur({ width, height, os: "android" });
  /* eslint-disable @typescript-eslint/no-require-imports */
  const React = require("react");
  const TestRenderer = require("react-test-renderer");
  const { StyleSheet } = require("react-native");
  const { GlobalEmergencyStop } = require("@/components/ui/GlobalEmergencyStop");
  /* eslint-enable @typescript-eslint/no-require-imports */
  type Dugum = { props: Record<string, unknown> };
  type Kok = { findAll: (f: (n: Dugum) => boolean) => Dugum[] };
  // ⚠️ İKİ TUZAK: (a) `let x = null` + act geri-çağrısında atama TS'te `never`'a daralır → tutucu
  // NESNE kullanılır; (b) `.root` act'in İÇİNDE okunamaz (ağaç henüz commit edilmemiş →
  // "Can't access .root on unmounted test renderer"; tam süitte kırmızı verdi) → act'ten SONRA okunur.
  const tut: { agac?: { root: Kok } } = {};
  TestRenderer.act(() => {
    tut.agac = TestRenderer.create(React.createElement(GlobalEmergencyStop, { compact }));
  });
  if (!tut.agac) throw new Error("düğme çizilemedi");
  const adaylar = tut.agac.root.findAll(
    (n: Dugum) => n.props?.accessibilityLabel === "Acil durdur" && n.props?.style !== undefined
  );
  if (!adaylar.length) throw new Error("ACİL DURDUR düğmesi bulunamadı");
  return StyleSheet.flatten(adaylar[0].props.style) as Record<string, number>;
}

describe("HASTA GÜVENLİĞİ — dokunma tabanı ölçekten bağımsız", () => {
  const cihazlar: [string, number, number][] = [
    ["dar telefon (ölçek tabanı 0,85)", 320, 568],
    ["referans telefon", 375, 812],
    ["tablet dikey", 768, 1024],
  ];

  it.each(cihazlar)("KRİTİK: %s → minHeight >= 44", (_ad, w, h) => {
    expect(dugmeStili(w, h).minHeight).toBeGreaterThanOrEqual(44);
  });

  it("KRİTİK: 320 px'te KOMPAKT çizim de tabanı korur (yatay telefon)", () => {
    expect(dugmeStili(568, 320, true).minHeight).toBeGreaterThanOrEqual(44);
  });

  it("dar telefonda düğme hâlâ ekranın büyük kısmını kaplar (maxWidth kısıtı değil)", () => {
    const st = dugmeStili(320, 568);
    expect(st.maxWidth).toBeGreaterThan(320);
    expect(st.alignSelf).toBe("stretch");
  });
});
