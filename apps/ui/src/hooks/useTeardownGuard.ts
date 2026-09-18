// Author: mertaygn, cglrgrkn
/**
 * useTeardownGuard — uygulama KABUĞUNU söken eylemler için hasta-güvenliği kapısı.
 * ================================================================================
 * "Çıkış Yap" ve "Farklı Bir Profile Geçiş Yap", `session`/`userMode` null'landığı anda
 * `PemfApp`'in MainRouter'ını (AppShell + Dashboard + ControlScreen + SessionProgressCard)
 * KOMPLE söker. ACİL DURDUR yalnız o ağaçta yaşadığından, tedavi sürerken bu eylemler
 * operatörü durdurma kontrolü OLMAYAN bir ekranda bırakıyordu: bobinler hayvanın üzerinde
 * çalışmaya devam ederken geri dönmek için yeniden e-posta+şifre girmek gerekiyordu.
 * Üstelik "Çıkış Yap", profil menüsünde asıl tıklanmak istenen üç profil satırının hemen
 * altında AYNI stille duruyor → yanlış dokunuş çok olası.
 *
 * Kapı: donanım çalışıyorsa ONAY iste; onaylanırsa ÖNCE durdur, sonra sökmeye izin ver.
 * Durdurma teyit edilemezse eylemi İPTAL et (operatör durdurma kontrolünü kaybetmesin).
 */
import { useCallback } from "react";
import { platformAlert, platformConfirm } from "@/services/apiClient";
import {
  performEmergencyStop,
  EMERGENCY_STOP_UNCONFIRMED_TITLE,
  EMERGENCY_STOP_UNCONFIRMED_BODY,
} from "@/services/emergencyStop";
import { useLiveData } from "@/context/LiveDataContext";

/** Donanım BOŞTAYKEN istenen (opsiyonel) ikinci onay — bkz. `TeardownOpts`. */
export interface IdleConfirm {
  title: string;
  body: string;
  confirmLabel?: string;
}

export interface TeardownOpts {
  /**
   * Donanım BOŞTAYKEN de onay iste. Hasta güvenliği kapısı yalnız bobinler ÇALIŞIRKEN devreye
   * girer; boştayken tek dokunuş yeter. "Çıkış Yap" nav'da Ayarlar'ın hemen altına geldiği için
   * (2026-08-06) yanlış dokunuş riski arttı ve kazara çıkış, mobilde e-posta+şifre tekrarı demek.
   * Bu yüzden yıkıcı ama tıbbi olmayan onay AYRI ve OPSİYONEL: verilmezse davranış eskisiyle
   * BİREBİR aynı kalır (boşta soru sorulmaz) → mevcut çağrı yerleri etkilenmez.
   */
  confirmWhenIdle?: IdleConfirm;
}

export function useTeardownGuard() {
  const { snapshot } = useLiveData();

  /**
   * @param actionLabel Kullanıcıya gösterilecek eylem adı ("Çıkış yapmak", "Profil değiştirmek").
   * @param opts Opsiyonel: donanım boştayken de onay iste (bkz. TeardownOpts).
   * @returns Eyleme devam edilebilir mi.
   */
  return useCallback(
    async (actionLabel: string, opts?: TeardownOpts): Promise<boolean> => {
      // Seans bayrağından BAĞIMSIZ kontrol: AI Pro / fiziksel / başka istemci bobinleri
      // enerjileyebilir ama session_* yayınlamaz → `isActive` false kalır (DashboardScreen'deki
      // `hardwareRunning` mantığının aynısı).
      const running = (snapshot.coils ?? []).filter((c) => c?.running).length;
      const active = snapshot.activeTreatment?.isActive === true;
      if (!running && !active) {
        // Boşta: tıbbi risk YOK. Yalnız çağıran açıkça istediyse (kazara dokunuş koruması) sor.
        if (!opts?.confirmWhenIdle) return true;
        const { title, body, confirmLabel } = opts.confirmWhenIdle;
        return platformConfirm(title, body, confirmLabel ?? "Devam et");
      }

      const ok = await platformConfirm(
        "Seans sürüyor",
        `${running > 0 ? `${running} bobin ÇALIŞIYOR. ` : "Aktif bir seans var. "}` +
          `${actionLabel} tüm durdurma kontrollerini ekrandan kaldırır.\n\n` +
          "Devam edilirse bobinler ÖNCE durdurulacak.",
        "Durdur ve devam et"
      );
      if (!ok) return false;

      const { confirmed } = await performEmergencyStop();
      if (!confirmed) {
        // Durdurma teyit edilemedi → kabuğu SÖKME. Operatörün elinde ACİL DURDUR kalsın.
        platformAlert(
          EMERGENCY_STOP_UNCONFIRMED_TITLE,
          `${EMERGENCY_STOP_UNCONFIRMED_BODY}\n\nGüvenlik için işlem iptal edildi — ekranda kalıyorsunuz.`
        );
        return false;
      }
      return true;
    },
    [snapshot]
  );
}
