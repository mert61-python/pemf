// Author: mertaygn, cglrgrkn
/**
 * SUPABASE OTURUM DEPOLAMASI — PARÇALI YAZIM GEÇİCİ HATADA OTURUMU KAYBETTİRİYORDU (bulgu 22, cid. 5).
 *
 * `_secSet` parçalı yolda ÖNCE eski parçaları siliyor, sonra yeni parçaları yazıyor, meta'yı EN SON
 * güncelliyor ve hiç `try/catch` içermiyordu (kardeşleri `_secGet`/`_secRemove`'da var). Tek bir
 * geçici `SecureStore.setItemAsync` hatası (cihaz kilitli / keystore meşgul) ya da birkaç ms'lik
 * pencerede OS'un süreci öldürmesi hâlinde meta artık VAR OLMAYAN parçalara işaret ediyordu →
 * `_secGet` kalıcı `null` → veteriner bir sonraki açılışta e-posta+şifre ile TEKRAR GİRİŞ yapıyordu.
 *
 * ⚠️ PARÇALI YOL İSTİSNA DEĞİL, NORMAL YOL: gerçekçi bir GoTrue oturumu 2735 karakter ölçüldü
 * (profilsiz oturum bile 2074) → 1800 karakterlik parça sınırının altına HİÇ inmiyor.
 * `@supabase/auth-js`in `_saveSession`ı `setItemAsync` etrafında try/catch içermiyor (kaynak
 * okundu) ve alternatif token kaynağı yok — telafi eden bir katman da yok.
 *
 * ⚠️ YALNIZ NATIVE: klinik makinesinin arayüzü web bundle'dır ve orada parçalama YOK → tedaviyi
 * yapan operatörün konsolu etkilenmiyor. Bu yüzden testler `Platform.OS = "ios"` ile koşar; web
 * dalında koşmak testi ANLAMSIZ yeşile çevirirdi.
 *
 * ⚠️ YAZIM SIRASI BİLEREK DEĞİŞTİRİLMEDİ (2. test bunu kilitler): tutarlı ama BAYAT bir oturum
 * bırakmak, GoTrue'nun iptal edilmiş `refresh_token` ile tazeleme denemesine (400 → `_removeSession`
 * → `SIGNED_OUT`) yol açar ve tedavi ORTASINDA AppShell + ACİL DURDUR ekrandan kalkar.
 */
import { Platform } from "react-native";

// ── expo-secure-store: kontrol edilebilir in-memory mockDepo ─────────────────────
const mockDepo = new Map<string, string>();
const mockCtl = { failNextSets: 0, failAllSets: false, setCagrisi: 0 };

jest.mock("expo-secure-store", () => ({
  getItemAsync: async (k: string) => (mockDepo.has(k) ? mockDepo.get(k)! : null),
  setItemAsync: async (k: string, v: string) => {
    mockCtl.setCagrisi += 1;
    if (mockCtl.failAllSets) throw new Error("keystore mesgul (taklit)");
    if (mockCtl.failNextSets > 0) {
      mockCtl.failNextSets -= 1;
      throw new Error("keystore mesgul (taklit)");
    }
    mockDepo.set(k, v);
  },
  deleteItemAsync: async (k: string) => {
    mockDepo.delete(k);
  },
}));

// `createClient`ı yakala → gerçek depolama adaptörünü oradan al (üretimde kullanılan nesne).
const mockTutucu: { opts: { auth?: { storage?: unknown } } | null } = { opts: null };
jest.mock("@supabase/supabase-js", () => ({
  createClient: (_u: string, _k: string, o: unknown) => {
    mockTutucu.opts = o as { auth?: { storage?: unknown } };
    return { auth: {} };
  },
}));

type Adaptor = {
  getItem: (k: string) => Promise<string | null>;
  setItem: (k: string, v: string) => Promise<void>;
  removeItem: (k: string) => Promise<void>;
};

require("@/services/supabaseAuth");

const st = () => mockTutucu.opts!.auth!.storage as Adaptor;
const K = "sb-oturum";

beforeEach(() => {
  mockDepo.clear();
  mockCtl.failNextSets = 0;
  mockCtl.failAllSets = false;
  mockCtl.setCagrisi = 0;
  // ⚠️ jest-expo preset'i `defaultPlatform: "ios"` kullanıyor ama açıkça yazmak, preset değişirse
  // testin sessizce WEB dalına kayıp anlamsız yeşile dönmesini engeller.
  (Platform as unknown as { OS: string }).OS = "ios";
});

it("ÖN KOŞUL: gerçekçi oturum boyutu PARÇALI yolu kullanır", async () => {
  // Parçalı yol koşmuyorsa aşağıdaki testler kusuru hiç ölçmez (yanlış-yeşil kalkanı).
  await st().setItem(K, "A".repeat(2600));
  expect(mockDepo.get(K)!.startsWith("__chunks__:")).toBe(true);
  expect(await st().getItem(K)).toBe("A".repeat(2600));
});

it("KRİTİK: GEÇİCİ keystore hatası oturumu KAYBETTİRMEZ", async () => {
  await st().setItem(K, "A".repeat(2600));
  expect(await st().getItem(K)).toBe("A".repeat(2600));

  mockCtl.failNextSets = 1; // ilk parça yazımı bir kez patlar (cihaz kilitli / keystore meşgul)
  await st().setItem(K, "B".repeat(2600));

  expect(await st().getItem(K)).toBe("B".repeat(2600));
});

it("KALICI hata BAYAT oturum BIRAKMAZ (sıra değiştirme çözümünü reddeder)", async () => {
  // ⚠️ REDDEDİLEN ALTERNATİF KAPISI: "önce yeni parçaları yaz, sonra meta, en son eski artıkları
  // sil" biçiminde bir yama diskte TUTARLI ama BAYAT bir oturum bırakır. O bayat/iptal edilmiş
  // refresh_token ile GoTrue tazeleme dener, 400 alır ve tedavi ORTASINDA SIGNED_OUT olur.
  // Bir yeniden giriş, tedavi ortasında oturumun düşmesinden iyidir.
  await st().setItem(K, "A".repeat(2600));

  mockCtl.failAllSets = true;
  await expect(st().setItem(K, "B".repeat(2600))).rejects.toBeDefined();

  expect(await st().getItem(K)).toBeNull();
});

it("YÜKSELTME KAPISI: eski biçimde yazılmış parçalar okunabilmeli", async () => {
  // Nesil eki (`key.<gen>.i`) gibi bir "düzeltme", kurulu HER cihazın zorla yeniden girişine yol
  // açar. Bu test o yolu kapatır: diskteki eski biçim aynen okunmalı.
  mockDepo.set(K, "__chunks__:2");
  mockDepo.set(`${K}.0`, "X".repeat(1800));
  mockDepo.set(`${K}.1`, "Y".repeat(800));

  expect(await st().getItem(K)).toBe("X".repeat(1800) + "Y".repeat(800));
});

it("tek denemede başarılı yazım FAZLADAN çağrı yapmaz (yeniden deneme yalnız hatada)", async () => {
  mockCtl.setCagrisi = 0;
  await st().setItem(K, "kisa-deger");
  expect(mockCtl.setCagrisi).toBe(1);
});
