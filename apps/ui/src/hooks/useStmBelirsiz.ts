// Author: mertaygn, cglrgrkn
/**
 * "BOBİN DURUMU BİLİNMİYOR" — STM belirsizliği kuralının TEK kaynağı (D1.E03 · A-59).
 *
 * STM seri bağlantısı koptuğunda `LiveDataContext.normalizeStmCoils` STM bobinlerini `running:false` yapar. Bu "bobin
 * DURDU" değil "durum BİLİNMİYOR" demektir (USB kopukken yazılım STOP'u karta ulaşamaz). KURAL: bir kez "çalışıyor"
 * görüldüyse (bobin ya da aktif tedavi), STM yeniden ÇEVRİMİÇİ olup "durdu" diyene kadar durum BELİRSİZ kalır. Hiç
 * çalışmamış (donanımsız/demo) makinede belirsizlik YOK — gürültü yapılmaz.
 *
 * Kullananlar: `GlobalEmergencyStop` (düğme "(bağlantı yok)" ile ekranda kalır) ve `LiveDataProvider`
 * (`donanimBelirsiz` → `useTeardownGuard`: belirsiz = ÇALIŞIYOR sayılır, sahip kararı A-59). Kural burada bir kez yazılır;
 * kilidin ömrü kullanan bileşeninkidir (sağlayıcıda uygulama boyu).
 *
 * ⚠️ GÜVENLİK LİMİTİ DEĞİLDİR: acil durdurmayı hiçbir koşulda kapılamaz (Ö.4-Y8) — tersine, `true` iken durdurma
 * GÖRÜNÜR olmalı ve kabuk sökümü önce durdurmalıdır.
 */
import { useEffect, useState } from "react";
import type { DashboardSnapshot } from "@/types/domain";

export function useStmBelirsiz(snapshot: Partial<DashboardSnapshot> | undefined): boolean {
  const running = (snapshot?.coils ?? []).filter((c) => c?.running).length;
  const active = snapshot?.activeTreatment?.isActive === true;
  const stmBelirsiz = snapshot?.stm !== "online";
  const [kilit, setKilit] = useState(false);
  useEffect(() => {
    if (running > 0 || active) setKilit(true);
    else if (!stmBelirsiz) setKilit(false);
  }, [running, active, stmBelirsiz]);
  return stmBelirsiz && kilit && running === 0 && !active;
}
