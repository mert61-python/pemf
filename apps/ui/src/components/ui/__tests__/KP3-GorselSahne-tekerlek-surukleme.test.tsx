/**
 * KP-3 C · GorselSahne tam ekran görüntüleyici — her test bir DAVRANIŞ iddiası:
 *  - Fare tekerleği: yukarı yakınlaştırır, aşağı uzaklaştırır (sığdırmanın altına inmez); sayfa kaydırması ENGELLENİR (`passive: false` +
 *    `preventDefault`); her yeniden kurulumda eski dinleyici kaldırılır (tek dinleyici), tam ekran kapanınca hiç dinleyici kalmaz.
 *  - Sürükleme: sığan görsel ortada kalır; yakınlaştırılmış görsel kaydırılır ama kenarın ötesine taşınmaz (görsel "kaybolmaz");
 *    ikinci sürükleme kaldığı yerden sürer.
 *  - Uzaklaştır düğmesi bir basamak geri iner; Android geri tuşu (Modal `onRequestClose`) tam ekranı kapatır, sayfa korunur.
 * SAHTE (platform): DOM düğümünün `addEventListener`i (RN'de `onWheel` yok, ürün web düğümüne bağlanır) · dokunuş geçmişi (PanResponder girdisi).
 * GERÇEK: GorselSahne + PanResponder + zoom merdiveni.
 */
import React from "react";
import { Modal, View } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";
import { GorselSahne } from "@/components/ui/GorselSahne";
import type { SahneSayfasi } from "@/utils/gorselSahneSayfalari";

const YEDI: SahneSayfasi[] = [
  { k: "01_input", ad: "Girdi", uri: "file:///depo/foto.jpg" },
  { k: "02_phantom_detect", ad: "Tespit", uri: "data:image/jpeg;base64,B", image_w: 800, image_h: 600 },
  { k: "03_phantom_mask", ad: "Maske", uri: "data:image/jpeg;base64,C", image_w: 320, image_h: 240 },
  { k: "04_tumors", ad: "Tümörler", uri: "data:image/jpeg;base64,D", image_w: 1024, image_h: 768 },
  { k: "05_local_coords", ad: "Koordinat", uri: "data:image/jpeg;base64,E", image_w: 500, image_h: 900 },
  { k: "06_predictions", ad: "Tahmin", uri: "data:image/jpeg;base64,F", image_w: 1200, image_h: 400 },
  { k: "07_combined", ad: "Birleşik", uri: "data:image/jpeg;base64,G", image_w: 1600, image_h: 1067 },
];

type Api = ReturnType<typeof render>;
function olc(api: Api) {
  fireEvent(api.getByTestId("gorsel-sahne"), "layout", { nativeEvent: { layout: { width: 900, height: 400 } } });
  fireEvent(api.getByTestId("gorsel-sahne-kontrol"), "layout", { nativeEvent: { layout: { width: 900, height: 44 } } });
}
/** GorselSahne.test.tsx ile aynı: modal içindeki `onLayout` RNTL'de olayla ulaşmıyor → üretim işleyicisi doğrudan çağrılır. */
function tamEkranAc(api: Api, w = 600, h = 400) {
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));
  act(() => { api.getByTestId("gorsel-sahne-tam-alan").props.onLayout({ nativeEvent: { layout: { width: w, height: h } } }); });
}
const genislik = (api: Api) => api.getByTestId("gorsel-sahne-gorsel-tam").props.style.width as number;
const kaydirma = (api: Api) => api.getByTestId("gorsel-sahne-gorsel-tam").props.style.transform;
function dokunus(t: number, x: number, y: number, px: number, py: number) {
  return {
    touchHistory: {
      numberActiveTouches: 1, indexOfSingleActiveTouch: 0, mostRecentTimeStamp: t,
      touchBank: [{ touchActive: true, startPageX: 0, startPageY: 0, startTimeStamp: 0, currentPageX: x, currentPageY: y,
        currentTimeStamp: t, previousPageX: px, previousPageY: py, previousTimeStamp: t - 1 }],
    },
  };
}

it("tekerlek: yukarı yakınlaştırır, aşağı sığdırmaya döner; sayfa kaymaz; tek dinleyici, kapanınca hiç", () => {
  // ⚠️ PLATFORM: jest'te RN `View` SINIF bileşeniyle sahtelenir (@react-native/jest-preset mocks/View → mockComponent); `ref` ana
  // düğüme değil bu örneğe bağlanır → `createNodeMock` devreye GİRMEZ (ölçüldü). Web'deki DOM düğümünün `addEventListener`i bu
  // sınıfın prototipine YALNIZ tam ekran alanı için eklenir, test sonunda geri alınır.
  const aktif = new Set<(e: unknown) => void>();
  const secenekler: unknown[] = [];
  const proto = (View as unknown as { prototype: Record<string, unknown> }).prototype;
  const onceki = { ekle: proto.addEventListener, sil: proto.removeEventListener };
  const bu = (o: unknown) => (o as { props?: { testID?: string } }).props?.testID === "gorsel-sahne-tam-alan";
  proto.addEventListener = function (this: unknown, t: string, f: (e: unknown) => void, o?: unknown) {
    if (bu(this) && t === "wheel") { aktif.add(f); secenekler.push(o); }
  };
  proto.removeEventListener = function (this: unknown, t: string, f: (e: unknown) => void) {
    if (bu(this) && t === "wheel") aktif.delete(f);
  };
  try {
    tekerlekSenaryosu(aktif, secenekler);
  } finally {
    if (onceki.ekle === undefined) delete proto.addEventListener; else proto.addEventListener = onceki.ekle;
    if (onceki.sil === undefined) delete proto.removeEventListener; else proto.removeEventListener = onceki.sil;
  }
});

function tekerlekSenaryosu(aktif: Set<(e: unknown) => void>, secenekler: unknown[]) {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  tamEkranAc(api);
  expect(aktif.size).toBe(1);
  expect(secenekler.every((o) => JSON.stringify(o) === JSON.stringify({ passive: false }))).toBe(true);
  const tekerlek = () => [...aktif][0];
  const taban = genislik(api);
  const engel = jest.fn();
  act(() => { tekerlek()({ deltaY: -120, preventDefault: engel }); });
  expect(genislik(api)).toBeGreaterThan(taban);
  expect(engel).toHaveBeenCalledTimes(1);
  for (let i = 0; i < 6; i++) act(() => { tekerlek()({ deltaY: 120, preventDefault: engel }); });
  expect(genislik(api)).toBe(taban);
  expect(aktif.size).toBe(1);
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran-kapat"));
  expect(aktif.size).toBe(0);
}

it("sürükleme: sığan görsel ortada; yakınlaştırılmış görsel kaydırılır ama kenarı aşmaz; ikinci sürükleme kaldığı yerden", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  tamEkranAc(api);
  const alan = () => api.getByTestId("gorsel-sahne-tam-alan");
  act(() => { alan().props.onResponderGrant(dokunus(1, 0, 0, 0, 0)); });
  act(() => { alan().props.onResponderMove(dokunus(2, 100, 40, 0, 0)); });
  expect(kaydirma(api)).toEqual([{ translateX: 0 }, { translateY: 0 }]);

  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  const g = genislik(api);
  expect(g).toBeGreaterThan(600);
  const kenar = (g - 600) / 2;
  act(() => { alan().props.onResponderGrant(dokunus(10, 0, 0, 0, 0)); });
  act(() => { alan().props.onResponderMove(dokunus(11, 100, 40, 0, 0)); });
  expect(kaydirma(api)[0]).toEqual({ translateX: 100 });
  act(() => { alan().props.onResponderMove(dokunus(12, 100 + 5000, 40, 100, 40)); });
  expect(kaydirma(api)[0].translateX).toBeCloseTo(kenar, 0); // sınır: görsel kenarı görünümün kenarında durur
  act(() => { alan().props.onResponderGrant(dokunus(20, 0, 0, 0, 0)); });
  act(() => { alan().props.onResponderMove(dokunus(21, -50, 0, 0, 0)); });
  expect(kaydirma(api)[0].translateX).toBeCloseTo(kenar - 50, 0);
});

it("uzaklaştır bir basamak iner; Android geri tuşu tam ekranı kapatır, sayfa korunur", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-sonraki"));
  const sayac = api.getByTestId("gorsel-sahne-sayac").props.children;
  tamEkranAc(api);
  const taban = genislik(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  expect(genislik(api)).toBeGreaterThan(taban);
  fireEvent.press(api.getByTestId("gorsel-sahne-uzaklastir"));
  expect(genislik(api)).toBe(taban);
  act(() => { api.UNSAFE_getByType(Modal).props.onRequestClose(); });
  expect(api.queryByTestId("gorsel-sahne-tam-ekran-kap")).toBeNull();
  expect(api.getByTestId("gorsel-sahne-sayac").props.children).toEqual(sayac);
});
