// Author: mertaygn
/**
 * useCokluSecim — toplu silme seçimi (sahip bildirimi 2026-09-12).
 * ================================================================
 * "toplu sil seçeneği eksik seans geçmişi tabında kullanıcı tek tek silmek zorunda kalıyor."
 * + "hasta veri tabanında da toplu sil butonu lazım."
 *
 * ⚠️ BU DOSYANIN ASIL KAPISI "HAYALET SEÇİM"DİR:
 * Operatör kayıt seçer, sonra aramayı/kapsamı değiştirir. Seçilenlerin bir kısmı artık
 * EKRANDA DEĞİLDİR. Ham bir `Set` tutulsaydı "Sil", operatörün O AN GÖREMEDİĞİ kayıtları da
 * silerdi — geri alınamaz bir işlemde görünmeyen yan etki. Kesişim bunu imkânsız kılar.
 */
import { act, renderHook } from "@testing-library/react-native";
import { CokluSecim, useCokluSecim } from "@/hooks/useCokluSecim";

/** `renderHook`un tip çıkarımı `initialProps` ile `unknown`a düşüyor → açık tip. */
type Kap = { ids: number[] };

// ============================================================================
// 1. ⚠️ ASIL KAPI — HAYALET SEÇİM
// ============================================================================

test("KRITIK: gorunmez olan kayit secimden DUSER (hayalet secim yok)", () => {
  // MUTASYON: `seciliKimlikler`i `[...ham]` yap (kesişimi kaldır) → KIRMIZI.
  const { result, rerender } = renderHook<CokluSecim<number>, Kap>(({ ids }) => useCokluSecim(ids), {
    initialProps: { ids: [1, 2, 3] },
  });
  act(() => {
    result.current.degistir(1);
    result.current.degistir(3);
  });
  expect(result.current.seciliKimlikler).toEqual([1, 3]);

  // Arama/kapsam değişti: 3 artık ekranda değil.
  rerender({ ids: [1, 2] });
  expect(result.current.seciliKimlikler).toEqual([1]);
  expect(result.current.seciliSayi).toBe(1);
  expect(result.current.secilimi(3)).toBe(false);
});

test("KRITIK: gorunur olunca secim GERI GELMEZ surprizi olmasin", () => {
  // ⚠️ Kesişim, ham seçimi silmez (yalnız gizler). Filtre geri alınınca eski seçim
  // "kendiliğinden" geri gelirse operatör onu fark etmeden "Sil"e basabilir.
  // Bu kapı davranışı BELGELER: geri gelir. Kabul edilebilir, ÇÜNKÜ silme her durumda
  // sayıyı gösteren bir onay diyaloğundan geçer ve şerit "N kayıt seçildi" yazar.
  const { result, rerender } = renderHook<CokluSecim<number>, Kap>(({ ids }) => useCokluSecim(ids), {
    initialProps: { ids: [1, 2, 3] },
  });
  act(() => result.current.degistir(3));
  rerender({ ids: [1, 2] });
  expect(result.current.seciliSayi).toBe(0);
  rerender({ ids: [1, 2, 3] });
  expect(result.current.seciliKimlikler).toEqual([3]);
});

// ============================================================================
// 2. TEMEL DAVRANIŞ
// ============================================================================

test("degistir SECER ve SECIMI KALDIRIR", () => {
  const { result } = renderHook(() => useCokluSecim([1, 2]));
  act(() => result.current.degistir(1));
  expect(result.current.secilimi(1)).toBe(true);
  act(() => result.current.degistir(1));
  expect(result.current.secilimi(1)).toBe(false);
  expect(result.current.seciliSayi).toBe(0);
});

test("KRITIK: tumunuSec YALNIZ GORUNENLERI secer", () => {
  // ⚠️ "Tümünü Seç" adı yanıltıcı olabilir: filtre aktifken bu, TÜM VERİTABANINI değil
  // ekrandakileri seçmelidir. Aksi halde arama yapan operatör görmediği kayıtları silerdi.
  const { result } = renderHook(() => useCokluSecim([5, 6]));
  act(() => result.current.tumunuSec());
  expect(result.current.seciliKimlikler).toEqual([5, 6]);
  expect(result.current.hepsiSecili).toBe(true);
});

test("BOS listede hepsiSecili FALSE (dugme yanlis etiket gostermesin)", () => {
  // `0 === 0` tuzağı: boş listede "Seçimi Temizle" yazan bir düğme anlamsızdır.
  const { result } = renderHook(() => useCokluSecim<number>([]));
  expect(result.current.hepsiSecili).toBe(false);
});

test("KRITIK: secim kipi KAPANINCA secim TEMIZLENIR", () => {
  // ⚠️ Açık kalan seçim, kullanıcı başka sekmeye gidip döndüğünde "neyi seçmiştim?"
  // sorusunu doğurur ve bir sonraki "Sil" tıklamasını tehlikeli yapar.
  //
  // MUTASYON: `secimModunuDegistir` içindeki `setHam(new Set())` satırını sil → KIRMIZI.
  const { result } = renderHook(() => useCokluSecim([1, 2]));
  act(() => result.current.secimModunuDegistir());
  expect(result.current.secimModu).toBe(true);
  act(() => result.current.degistir(1));
  expect(result.current.seciliSayi).toBe(1);
  act(() => result.current.secimModunuDegistir());
  expect(result.current.secimModu).toBe(false);
  act(() => result.current.secimModunuDegistir());
  expect(result.current.seciliSayi).toBe(0);
});

test("temizle secimi bosaltir ama KIPI KAPATMAZ", () => {
  const { result } = renderHook(() => useCokluSecim([1, 2]));
  act(() => result.current.secimModunuDegistir());
  act(() => result.current.tumunuSec());
  act(() => result.current.temizle());
  expect(result.current.seciliSayi).toBe(0);
  expect(result.current.secimModu).toBe(true);
});

test("KRITIK: secim sirasi EKRANDAKI sirayi izler", () => {
  // ⚠️ `Set` ekleme sırasını korur; kullanıcı 3'ü önce seçtiyse ham sıra [3,1] olur.
  // Silme isteği ekrandaki sırayla gitmeli ki sunucu logu operatörün gördüğüyle eşleşsin.
  const { result } = renderHook(() => useCokluSecim([1, 2, 3]));
  act(() => {
    result.current.degistir(3);
    result.current.degistir(1);
  });
  expect(result.current.seciliKimlikler).toEqual([1, 3]);
});

test("metin kimliklerle de calisir (hasta id'leri uuid)", () => {
  const { result } = renderHook(() => useCokluSecim(["a", "b"]));
  act(() => result.current.degistir("b"));
  expect(result.current.seciliKimlikler).toEqual(["b"]);
});
