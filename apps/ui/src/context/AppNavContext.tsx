// Author: mertaygn, cglrgrkn
/**
 * AppNavContext — hafif uygulama-içi navigasyon + seçili hasta paylaşımı.
 * ====================================================================
 * PemfApp'te route state'i var ama ekranlar ona erişemiyordu (patient→session
 * stub'unun sebebi). Bu context: navigateTo(route) + seçili hasta'yı paylaşır.
 * Böylece Hastalar ekranından "Seans Başlat" → Kontrol ekranına gidip hastayı
 * seansta kullanabiliriz.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { useOperatorOptional } from "@/context/OperatorContext";
import type { RouteKey } from "@/types/domain";

export interface SelectedPatient {
  id?: string;
  name?: string;
  species?: string;
}

/**
 * AP-B1 (S-AP.1, sahip 13 Kasım 2026 "Seans sürsün"): Kontrol ekranının BU UYGULAMA OTURUMUNDAKİ belleği — rota / sekme değişince ekran
 * sökülse de son sekme ve AI Pro panelinin seçimleri dönüşte geri gelir. KALICI DEĞİL (diske / hesaba yazılmaz: "profil seçimi kalıcı
 * değil" ilkesi) ve kimlik değişince SİLİNİR (O-A3.6 deseni). Seansın / önizlemenin SÜRÜP SÜRMEDİĞİ bellekten değil sunucudan
 * (`/ai/pro/status`) okunur — bellek yalnız seçimleri taşır.
 */
export interface KontrolHafizasi {
  sekme?: "automatic" | "manual" | "aipro";
  aiPro?: { hedefModeli: string; kosulsuz: boolean; frek: number; duration: string; organId: number };
}

interface AppNavValue {
  navigateTo: (route: RouteKey) => void;
  selectedPatient: SelectedPatient | null;
  setSelectedPatient: (p: SelectedPatient | null) => void;
  /**
   * AI Hub'dan Kontrol ekranına taşınan AI Pro HEDEF MODELİ ön-seçimi (Faz 3, araştırma).
   *
   * Akış: araştırmacı AI Hub'da fantom/petri ANALİZİ yapar, "Bu hedefe AI Pro seansı" der;
   * Kontrol ekranı açılır ve model kartı ZATEN seçili gelir. TEK KULLANIMLIKtır: panel değeri
   * uygulayınca temizler, böylece sonraki ziyaretlerde kullanıcının seçimini EZMEZ.
   *
   * ⚠️ AI Hub burada YALNIZ niyeti taşır; hiçbir `/ai/pro/*` çağrısı yapmaz (otonom onay kapısı
   * yalnız Kontrol → AI Pro panelinde — bkz. aiHubOtonomOnayKapisi testi).
   */
  aiProModeli: string;
  setAiProModeli: (m: string) => void;
  /** AP-B1: Kontrol belleği (yalnız sağlayıcı varken; yoksa — tek başına çizilen ekran / test — bellek YOK, davranış eskisi). */
  kontrolHafizasi?: MutableRefObject<KontrolHafizasi>;
}

const AppNavContext = createContext<AppNavValue>({
  navigateTo: () => {},
  selectedPatient: null,
  setSelectedPatient: () => {},
  aiProModeli: "",
  setAiProModeli: () => {},
});

export function AppNavProvider({
  navigateTo,
  children,
}: {
  navigateTo: (route: RouteKey) => void;
  children: React.ReactNode;
}) {
  const [selectedPatient, setSelectedPatient] = useState<SelectedPatient | null>(null);
  const [aiProModeli, setAiProModeli] = useState("");
  const kontrolHafizasi = useRef<KontrolHafizasi>({});
  // ⚠️ O-A3.6 (2-B incelemesi): seçili hasta KİMLİĞE bağlıdır. Operatör değişince ya da kilitlenince (kimlik düşer) seçim
  // DÜŞER — eskiden kalıyordu: "Kilitle"den sonra önceki hekimin seçtiği hastaya kimliksiz (sahipsiz) analiz/seans
  // başlatılabiliyordu. Kimlik aynı kaldıkça seçim korunur (Kural 2: kimlik oturum e-postası, değişmez). Sağlayıcı yoksa
  // (eski testler) kimlik '' → hiç değişmez. Kapı: screens/__tests__/aiHubKimlikDegisimi.OA36.web.test.tsx.
  const kimlik = (useOperatorOptional()?.operatorEmail || "").toLowerCase();
  const sonKimlik = useRef(kimlik);
  useEffect(() => {
    if (sonKimlik.current === kimlik) return;
    sonKimlik.current = kimlik;
    setSelectedPatient(null);
    kontrolHafizasi.current = {}; // AP-B1: önceki hekimin seçimleri yeni kimliğe taşınmaz
  }, [kimlik]);
  // DÜŞÜK fix: value'yu memoize et → her render'da yeni obje üretip tüm useAppNav tüketicilerini
  // gereksiz yere render etme (setSelectedPatient stabil setter, navigateTo stabil prop).
  const value = useMemo(
    () => ({ navigateTo, selectedPatient, setSelectedPatient, aiProModeli, setAiProModeli, kontrolHafizasi }),
    [navigateTo, selectedPatient, aiProModeli],
  );
  return (
    <AppNavContext.Provider value={value}>
      {children}
    </AppNavContext.Provider>
  );
}

export function useAppNav(): AppNavValue {
  return useContext(AppNavContext);
}
