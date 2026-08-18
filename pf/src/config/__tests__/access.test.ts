// Author: mertaygn, cglrgrkn
/**
 * ROUTE_ACCESS — profil→rota kapısı. Bu tablo TIBBİ-GÜVENLİK kapısıdır (yanlış profile
 * cihaz/tedavi ekranı sızmamalı) ve hem PemfApp render'ı hem AppShell navigasyonu onu okur;
 * bugüne kadar HİÇ testi yoktu → sessizce sürüklenebiliyordu.
 *
 * 2026-08-06 SAHİP KARARI: araştırma profilinin "CİHAZ YOK" izolasyonu BİLEREK kaldırıldı;
 * control/sensors/kpi/simulator eklendi. Bu testler kararı kilitler ve pet_owner izolasyonunun
 * bu değişiklikten ETKİLENMEDİĞİNİ kanıtlar.
 */
import { ROUTE_ACCESS, canAccess } from "@/config/access";
import type { RouteKey } from "@/types/domain";

const YENI_ROTALAR: RouteKey[] = ["control", "sensors", "kpi", "simulator"];

describe("araştırma profili (2026-08-06 kararı)", () => {
  it("KRİTİK: control/sensors/kpi/simulator rotalarına ERİŞİR", () => {
    for (const r of YENI_ROTALAR) {
      expect(canAccess("researcher", r)).toBe(true);
    }
  });

  it("eski rotaları KAYBETMEDİ (hasta/geçmiş/AI/ayarlar duruyor)", () => {
    for (const r of ["dashboard", "patients", "history", "ai", "ai_history", "settings"] as RouteKey[]) {
      expect(canAccess("researcher", r)).toBe(true);
    }
  });

  it("cihaz erişimi artık VETERİNER ile aynı kümede", () => {
    expect([...ROUTE_ACCESS.researcher].sort()).toEqual([...ROUTE_ACCESS.veterinarian].sort());
  });
});

describe("diğer profiller ETKİLENMEDİ", () => {
  // ⚠️ 2026-08-08 SAHİP KARARI: pet_owner'a "patients" EKLENDİ (AI analizi hasta seçimi
  // zorunlu kıldığı için ev sahibinin de kendi hayvanlarını yönetmesi gerekiyor). Bu testin
  // KORUDUĞU ASIL ŞEY DEĞİŞMEDİ: CİHAZ/TEDAVİ rotaları ev sahibine hâlâ KAPALI.
  it("KRİTİK: pet_owner CİHAZ/TEDAVİ rotalarını GÖREMEZ (izolasyonun asıl amacı)", () => {
    for (const r of YENI_ROTALAR as RouteKey[]) {   // control, sensors, kpi, simulator
      expect(canAccess("pet_owner", r)).toBe(false);
    }
    expect(canAccess("pet_owner", "history" as RouteKey)).toBe(false);  // tedavi geçmişi = klinik
  });

  it("pet_owner kendi rotalarını görür (hasta yönetimi DAHİL, cihaz HARİÇ)", () => {
    expect(ROUTE_ACCESS.pet_owner).toEqual(["dashboard", "patients", "ai", "ai_history", "settings"]);
  });

  it("pet_owner HASTALAR ekranına erişir — AI kapısı oraya yönlendiriyor", () => {
    // PatientGate'teki "Hasta Ekle" navigateTo("patients") çağırır; rota kapalı olsaydı
    // kullanıcı boş ekrana düşerdi (ölü buton).
    expect(canAccess("pet_owner", "patients")).toBe(true);
  });

  it("veterinarian tüm klinik rotalarına erişir", () => {
    for (const r of YENI_ROTALAR) {
      expect(canAccess("veterinarian", r)).toBe(true);
    }
  });
});

describe("kapı davranışı", () => {
  it("profil seçilmemişse (null) HİÇBİR rotaya erişilemez", () => {
    for (const r of ["dashboard", "control", "ai", "settings"] as RouteKey[]) {
      expect(canAccess(null, r)).toBe(false);
    }
  });

  it("'Ayarlar' üç profilde de var (çıkış ögesi nav'da onun ardından gelir)", () => {
    for (const m of ["pet_owner", "veterinarian", "researcher"] as const) {
      expect(canAccess(m, "settings")).toBe(true);
    }
  });

  it("SÖZLEŞME: 'logout' bir RouteKey DEĞİL — hiçbir profilin rota listesinde yer almaz", () => {
    // Çıkış, AppShell'de AKSİYON ögesidir: rota yapılırsa routeMeta/render-switch'e sahte ekran
    // girer ve alt barda KAYDIRARAK kazara oturum kapatılabilir (bkz. AppShell NavEntry yorumu).
    for (const m of ["pet_owner", "veterinarian", "researcher"] as const) {
      expect(ROUTE_ACCESS[m]).not.toContain("logout" as unknown as RouteKey);
    }
  });
});
