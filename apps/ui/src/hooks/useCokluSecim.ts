// Author: mertaygn
/**
 * ÇOKLU SEÇİM — toplu işlem (silme) için ortak seçim durumu.
 * ==========================================================
 * ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "toplu sil seçeneği eksik seans geçmişi tabında kullanıcı
 * tek tek silmek zorunda kalıyor." + "hasta veri tabanında da toplu sil butonu lazım."
 *
 * ⚠️ NEDEN ORTAK KANCA, NEDEN İKİ EKRANA AYRI AYRI YAZILMADI: iki kopya sessizce ayrışır —
 * biri aşağıdaki "hayalet seçim" korumasını taşır, öbürü taşımaz ve arıza yalnız TEK ekranda
 * yaşar (bu deponun tekrar eden sınıfı). Tek kanca, tek kural.
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * ⚠️ HAYALET SEÇİM — BU KANCANIN ASIL VAR OLMA SEBEBİ
 * ═══════════════════════════════════════════════════════════════════════════════
 * Operatör 5 kayıt seçer, sonra aramayı değiştirir ya da "Tüm Klinik"ten "Benim
 * Seanslarım"a geçer. Seçilen kayıtların bir kısmı artık EKRANDA DEĞİLDİR. Ham bir
 * `Set` tutulsaydı "Sil" düğmesi, operatörün O AN GÖREMEDİĞİ kayıtları da silerdi —
 * geri alınamaz bir işlemde görünmeyen bir yan etki.
 *
 * Bu yüzden `secili` HER OKUMADA görünen kimliklerle KESİŞTİRİLİR: ekranda olmayan bir
 * kimlik ne sayılır, ne silinir. Kesişim türetilmiş değerdir (`useEffect` ile budama
 * DEĞİL) → bir render gecikmesi penceresi bile oluşmaz.
 */
import { useCallback, useMemo, useState } from "react";

export interface CokluSecim<T extends string | number> {
  /** Seçim kipi açık mı (kapalıyken kartlar normal davranır). */
  secimModu: boolean;
  /** Seçim kipini aç/kapat. Kapanışta seçim TEMİZLENİR. */
  secimModunuDegistir: () => void;
  /** ⚠️ YALNIZ EKRANDA GÖRÜNEN seçili kimlikler (hayalet seçim budanmış). */
  seciliKimlikler: T[];
  seciliSayi: number;
  secilimi: (kimlik: T) => boolean;
  degistir: (kimlik: T) => void;
  /** Görünen TÜM kayıtları seç. */
  tumunuSec: () => void;
  /** Seçimi boşalt (seçim kipi AÇIK kalır). */
  temizle: () => void;
  /** Görünen her kayıt seçili mi (boş listede false). */
  hepsiSecili: boolean;
}

export function useCokluSecim<T extends string | number>(gorunenKimlikler: T[]): CokluSecim<T> {
  const [secimModu, setSecimModu] = useState(false);
  const [ham, setHam] = useState<Set<T>>(() => new Set());

  const gorunenSet = useMemo(() => new Set(gorunenKimlikler), [gorunenKimlikler]);

  // ⚠️ KESİŞİM: ham seçimden EKRANDA OLMAYAN her kimlik düşer (bkz. "hayalet seçim").
  // Sıra `gorunenKimlikler`den gelir → silme isteği ekrandaki sırayla gider (okunur log).
  const seciliKimlikler = useMemo(
    () => gorunenKimlikler.filter((k) => ham.has(k)),
    [gorunenKimlikler, ham],
  );

  const degistir = useCallback((kimlik: T) => {
    setHam((onceki) => {
      const yeni = new Set(onceki);
      if (yeni.has(kimlik)) yeni.delete(kimlik);
      else yeni.add(kimlik);
      return yeni;
    });
  }, []);

  const tumunuSec = useCallback(() => setHam(new Set(gorunenSet)), [gorunenSet]);
  const temizle = useCallback(() => setHam(new Set()), []);

  const secimModunuDegistir = useCallback(() => {
    setSecimModu((a) => {
      // ⚠️ KAPANIŞTA TEMİZLE: açık kalan bir seçim, kullanıcı başka sekmeye gidip döndüğünde
      // "neyi seçmiştim?" sorusunu doğurur ve bir sonraki "Sil" tıklamasını tehlikeli yapar.
      if (a) setHam(new Set());
      return !a;
    });
  }, []);

  return {
    secimModu,
    secimModunuDegistir,
    seciliKimlikler,
    seciliSayi: seciliKimlikler.length,
    secilimi: (kimlik: T) => ham.has(kimlik) && gorunenSet.has(kimlik),
    degistir,
    tumunuSec,
    temizle,
    hepsiSecili: gorunenKimlikler.length > 0 && seciliKimlikler.length === gorunenKimlikler.length,
  };
}
