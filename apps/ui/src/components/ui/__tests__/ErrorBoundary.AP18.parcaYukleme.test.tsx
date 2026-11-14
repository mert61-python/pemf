/**
 * AP-18 (istem 48 · S-AP.11, sahip "kök nedeni araştır"): 13-11 istemci günlüğünde HER açılışta bir "[FATAL] Requiring unknown module N".
 * KÖK NEDEN: Metro web'de `React.lazy` ekran parçası ilk denemede EŞZAMANLI aranır (async-require `importAll`); parça henüz yüklü değilse
 * Metro'nun korumalı yükleyicisi (`guardedLoadModule`) hatayı genel işleyiciye `reportFatalError` ile verir. Zincirdeki öntanımlı işleyici
 * (error-guard) hatayı YENİDEN FIRLATIR → Metro yedeği parçayı eşzamansız yükler ve ekran açılır. Kayıt sahte FATAL'dı. Gerçekten
 * yüklenemeyen parça ErrorBoundary'ye düşer ve ORADA ayrıca kaydedilir — bu yüzden bu tek ileti "non-fatal · chunk-load" sınıflanır;
 * önceki işleyiciye ölümcül olarak AYNEN iletilir (davranış aynı). Düzen `KP3-ErrorBoundary-genel-ag.test.tsx` ile aynı.
 */
const mockPost = jest.fn((..._a: unknown[]) => Promise.resolve(null));
jest.mock("@/services/apiClient", () => ({ apiPost: (...a: unknown[]) => mockPost(...a) }));


type Dinleyici = (e: unknown) => void;

// Rota RAPOR ANINDA okunur (yükleme anında değil) → sahte pencere test bitene dek yerinde kalır, sonra geri alınır.
let geriAl: (() => void) | undefined;
function kurVeYukle() {
  const dinleyiciler: Record<string, Dinleyici> = {};
  const g = global as unknown as { window?: unknown; ErrorUtils?: unknown };
  const ilkWindow = g.window;
  const ilkEU = g.ErrorUtils;
  const onceki = jest.fn();
  let yeni: ((e: unknown, f?: boolean) => void) | undefined;
  g.window = { addEventListener: (t: string, f: Dinleyici) => { dinleyiciler[t] = f; }, location: { hash: "#/kontrol" } };
  g.ErrorUtils = { getGlobalHandler: () => onceki, setGlobalHandler: (f: (e: unknown, x?: boolean) => void) => { yeni = f; } };
  geriAl = () => { g.window = ilkWindow; g.ErrorUtils = ilkEU; };
  jest.isolateModules(() => { require("@/components/ui/ErrorBoundary"); });
  return { dinleyiciler, onceki, yeni: yeni! };
}

beforeEach(() => mockPost.mockClear());
afterEach(() => { geriAl?.(); geriAl = undefined; });

it("KRİTİK AP-18: Metro parça yükleme 'unknown module' denemesi FATAL kaydedilmez; önceki işleyiciye AYNEN (ölümcül) iletilir", () => {
  const { onceki, yeni } = kurVeYukle();
  const h = new Error('Requiring unknown module "2725".');
  yeni(h, true);
  const govde = mockPost.mock.calls[0][1] as { message: string };
  expect(govde.message).toBe('[non-fatal · chunk-load] Requiring unknown module "2725".');
  expect(onceki).toHaveBeenCalledWith(h, true);
});

it("KARŞIT AP-18: başka ölümcül hata FATAL kalır", () => {
  const { yeni } = kurVeYukle();
  yeni(new Error("TypeError: x is undefined"), true);
  expect((mockPost.mock.calls[0][1] as { message: string }).message).toBe("[FATAL] TypeError: x is undefined");
});
