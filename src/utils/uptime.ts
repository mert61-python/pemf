/**
 * Uptime formatlama — backend snapshot'taki `startTime` (process başlangıç ISO'su) ile
 * şimdiki zaman arasındaki farkı "HH:MM:SS" olarak verir.
 *
 * Neden istemci tarafında: `/api/system/info` ucu `uptime` DÖNDÜRMÜYOR (dönen anahtarlar:
 * softwareVersion, hardwareVersion, deviceId, pairingCode, tunnelUrl, stmConnected, timestamp).
 * SystemInfoPanel eskiden `d.uptime` okuyordu → daima `undefined` → "Çalışma Süresi" hep "00:00:00"
 * takılıydı. Uptime artık WS snapshot'taki `system.startTime`'dan hesaplanır (endpoint sözleşmesi
 * değişmeden, backend rebuild gerektirmeden). Bkz. guii/REFACTOR_BUGS.md Faz F.
 *
 * Not: backend `startTime`'ı `datetime.now().isoformat()` (TZ'siz yerel) üretir; yerel cihazda
 * (aynı saha/LAN) istemci TZ'si backend ile hizalıdır. Geriye dönük/negatif fark 0'a kırpılır.
 */
export function formatUptime(startTimeIso: string | undefined | null, nowMs: number): string {
  if (!startTimeIso) return "00:00:00";
  const startMs = new Date(startTimeIso).getTime();
  if (!Number.isFinite(startMs)) return "00:00:00";
  const totalSec = Math.max(0, Math.floor((nowMs - startMs) / 1000));
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}
