// Author: mertaygn, cglrgrkn
/** Sayfa başlıkları (kabuk üst çubuğu) — `PemfApp` buradan okur (SG.G1 / G2: profile göre metin; test edilebilir tek kaynak). */
import type { RouteKey } from "@/types/domain";

export const routeMeta: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün Hangi Dostumuza Seans Yapıyoruz?" },
  control: { title: "Seans Kontrol Merkezi", subtitle: "Akıllı Reçeteler ve Cihaz Yönetimi" },
  sensors: { title: "Cihaz Durumu", subtitle: "Gerçek Zamanlı Sensör İzleme" },
  history: { title: "Seans Geçmişi", subtitle: "Geçmiş seansları incele ve rapor al." },
  patients: { title: "Hasta Kayıtları", subtitle: "Dostlarımızın bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve klinik göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın dostumuza etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis", subtitle: "Kamera üzerinden otonom ağrı analizi ve seans." },
  ai_history: { title: "AI Analiz Geçmişi", subtitle: "Tüm modellerin analiz sonuçları — şifreli, detaylı kayıt." },
  settings: { title: "Ayarlar", subtitle: "Cihaz tercihleri ve gelişmiş mod." },
};

/**
 * SG.G1 / G2 (sahip gözlemi 2026-10-13: "metinler de bu profillere göre uyarlanmalı … klinikle araştırma modunun alakası yok"):
 * araştırma profilinde "klinik / dostumuz / ağrı" dili YOK (karar #12 — `utils/profilSozlugu`). Yalnız FARKLI olanlar; geri kalan AYNEN.
 */
const arastirmaRouteMeta: Partial<Record<RouteKey, { title: string; subtitle: string }>> = {
  dashboard: { title: "Hoş Geldiniz", subtitle: "Bugün hangi örnekle çalışıyoruz?" },
  patients: { title: "Örnek / Denek Kayıtları", subtitle: "Araştırma örneklerinin bilgileri." },
  kpi: { title: "Performans Raporu", subtitle: "Cihaz ve araştırma göstergeleri." },
  simulator: { title: "Etki Simülasyonu", subtitle: "Manyetik alanın örnek üzerindeki etkisini görselleştirin." },
  ai: { title: "Akıllı Teşhis", subtitle: "Araştırma görüntü analizleri (fantom, petri, doku, hücre)." },
};

export function sayfaBasligi(userMode: string | null, route: RouteKey): { title: string; subtitle: string } {
  return (userMode === "researcher" && arastirmaRouteMeta[route]) || routeMeta[route];
}
