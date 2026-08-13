// Author: mertaygn, cglrgrkn
import { formatUptime } from "../uptime";

describe("formatUptime", () => {
  // TZ'siz ISO (backend datetime.now().isoformat() ile aynı biçim); startMs aynı yolla
  // hesaplandığı için test timezone-bağımsızdır.
  const start = "2026-07-07T10:00:00.000";
  const startMs = new Date(start).getTime();

  it("startTime yoksa (undefined/null) → 00:00:00", () => {
    expect(formatUptime(undefined, startMs)).toBe("00:00:00");
    expect(formatUptime(null, startMs)).toBe("00:00:00");
  });

  it("geçersiz tarih → 00:00:00", () => {
    expect(formatUptime("not-a-date", startMs)).toBe("00:00:00");
  });

  it("0 saniye → 00:00:00", () => {
    expect(formatUptime(start, startMs)).toBe("00:00:00");
  });

  it("elapsed'i HH:MM:SS olarak formatlar", () => {
    expect(formatUptime(start, startMs + 1000)).toBe("00:00:01");
    expect(formatUptime(start, startMs + 65 * 1000)).toBe("00:01:05");
    expect(formatUptime(start, startMs + (2 * 3600 + 3 * 60 + 4) * 1000)).toBe("02:03:04");
  });

  it("100+ saat de gösterir (padStart taşmaz)", () => {
    expect(formatUptime(start, startMs + 100 * 3600 * 1000)).toBe("100:00:00");
  });

  it("negatif fark (nowMs < startMs) → 00:00:00 (clamp)", () => {
    expect(formatUptime(start, startMs - 5000)).toBe("00:00:00");
  });
});

// Backend `startTime`'ı TZ'SİZ üretir (datetime.now().isoformat()); JS bunu İSTEMCİNİN yerel
// saatiyle yorumlar. Tünel üzerinden farklı saat diliminden bağlanınca fark saatlerce kayar:
// telefon geride ise sonuç NEGATİF çıkıp 0'a kırpılıyordu → panel "00:00:00"da TAKILI kalıyor ve
// cihaz yeni açılmış gibi görünüyordu (yanlış güvence). Artık "bilinmiyor" der.
describe("saat dilimi kayması (tünel/uzaktan erişim)", () => {
  const start = "2026-07-07T10:00:00.000";
  const startMs = new Date(start).getTime();

  it("KRİTİK: saatlerce ileri startTime (TZ kayması) '00:00:00' DEĞİL '—' verir", () => {
    expect(formatUptime(start, startMs - 3 * 3600_000)).toBe("—");
  });

  it("küçük fark (<60sn, NTP jitter) hâlâ 00:00:00 — gereksiz '—' gösterme", () => {
    expect(formatUptime(start, startMs - 20_000)).toBe("00:00:00");
  });
});
