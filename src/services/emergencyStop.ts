// Author: mertaygn, cglrgrkn
/**
 * emergencyStop — donanım acil durdurmanın TEK KAYNAĞI.
 * ======================================================
 * Eskiden bu mantık yalnız `useSessionControl` içindeydi. Sorun: acil durdurmayı çağırması gereken
 * her yer (çıkış yap, profil değiştir, kabuk-seviyesi E-stop) o hook'u mount etmek zorunda kalıyordu;
 * hook ise mount'ta `/session/active` çekip 2sn'lik mutabakat interval'i kuruyor → her tüketici
 * fazladan bir poll döngüsü demek. Mantık buraya alındı: hook'suz, yan-etkisiz, her yerden çağrılabilir.
 *
 * İki katman:
 *   1) Bridge ucu  POST /api/hardware/emergency_stop  → STM 1-5 + ESP 6-8'i tek seferde durdurur.
 *   2) Yedek       POST /api/session/stop + /api/hardware/command{stop_all_coils}
 * Her ikisi de zaman aşımlıdır; hiçbiri teyit veremezse `confirmed:false` döner ve ÇAĞIRAN
 * kullanıcıyı "fiziksel güç düğmesi" uyarısıyla bilgilendirmek ZORUNDADIR.
 */
import { apiPost, authHeaders } from "@/services/apiClient";
import { serviceConfig } from "@/services/config";

interface EmergencyStopResponse {
  /**
   * ⭐ TEK KAYNAK. Backend bunu `_stm_ok VE _esp_ok` olarak hesaplar (api_server._emergency_stop_all):
   * TÜM transport'lar doğrulanmadıkça false. İstemci bunu YENİDEN TÜRETMEZ.
   */
  confirmed?: boolean;
  status?: string;
  stmStopped?: boolean;
  mqttResults?: { mqtt?: string }[];
}
interface CommandResponse {
  status?: string;
}

/** Bridge ucunun zaman aşımı. Yedek yol apiPost'un kendi 8sn'lik timeout'unu kullanır. */
const BRIDGE_TIMEOUT_MS = 5000;

/**
 * Donanımı durdur. ASLA throw etmez.
 * @returns `confirmed` — donanımın durduğu SUNUCU TARAFINDAN teyit edildi mi.
 *          `false` ise bobinler hâlâ çalışıyor OLABİLİR; çağıran mutlaka uyarmalıdır.
 */
export async function performEmergencyStop(): Promise<{ confirmed: boolean }> {
  // 1) Bridge (tek atışta STM + ESP).
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), BRIDGE_TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetch(`${serviceConfig.bridgeBaseUrl}/hardware/emergency_stop`, {
        method: "POST",
        // GÜVENLİK/GECİKME: eskiden yalnız Content-Type gönderiliyordu. Uzaktan (tünel) erişimde
        // backend auth'u ZORUNLU kıldığından bu istek HER SEFERİNDE 401 alıyor, birincil yol
        // boşuna harcanıyor ve acil durdurma ancak yedek yoldan (saniyeler sonra) gerçekleşiyordu.
        headers: { "Content-Type": "application/json", ...authHeaders() },
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) throw new Error(`emergency_stop HTTP ${response.status}`);
    const data = (await response.json().catch(() => null)) as EmergencyStopResponse | null;
    // ⚠️ DENETİM 2026-08-09 (ENGEL) — HASTA GÜVENLİĞİ: teyit ARTIK backend'den okunuyor.
    // Eski hâli `stmStopped VEYA herhangi-bir-bobin-success` idi. Bu bir VEYA olduğu için:
    // STM durup 3 ESP bobininin ÜÇÜ birden başarısız olsa bile — ya da 8 bobinden yalnız 1'i
    // onaylansa bile — arayüz "durduruldu" diyordu. Backend AYNI yanıtta doğru cevabı
    // (`confirmed` = tüm transport'lar) zaten gönderiyordu; istemci onu yok sayıp kendi
    // gevşek kuralını uyguluyordu. Bir bobin hastanın üzerinde çalışmaya devam ederken
    // operatöre "kesildi" demek, bu ekrandaki en ağır hata sınıfıdır.
    if (data?.confirmed === true) return { confirmed: true };
    // 2xx ama teyit YOK (kısmi/başarısız) → yedek yolu da dene (aşağı düş).
  } catch {
    /* bridge erişilemedi → yedek yol */
  }

  // 2) Yedek: AYNI yetkili ucu standart istemciyle dene. Birincil yol ham `fetch` + bridge
  // adresini kullanır; bu ise apiPost'un taban adresi/auth'u/timeout'u üzerinden gider (tünel
  // dahil) → gerçekten FARKLI bir taşıma yolu, ama teyit yine tek ve doğru kaynaktan gelir.
  try {
    const r = await apiPost<EmergencyStopResponse | null>(
      "/hardware/emergency_stop", {}, null, { silent: true });
    if (r?.confirmed === true) return { confirmed: true };
  } catch {
    /* aşağıdaki son çareye düş */
  }

  // 3) Son çare: seansı kapat + STM'e STOP. ⚠️ Bu yol ESP 6-8'i KAPSAMAZ (yalnız STM 1-5).
  // Bu yüzden başarılı olsa bile `confirmed: false` döner: komutlar gönderilir ama ESP bobinlerinin
  // durduğuna dair HİÇBİR kanıt yoktur. Eskiden burada `status === "success"` teyit sayılıyordu —
  // STM'in durması, ESP bobinleri hastanın üzerinde çalışırken "hepsi kesildi" diye raporlanıyordu.
  try {
    await apiPost<CommandResponse | null>("/session/stop", {}, null, { silent: true });
    await apiPost<CommandResponse | null>(
      "/hardware/command",
      { command: "stop_all_coils", params: {} },
      null,
      { silent: true }
    );
  } catch {
    /* yut — zaten teyitsiz dönüyoruz */
  }
  return { confirmed: false };
}

/** Teyit edilemeyen durdurma için ORTAK uyarı metni (tüm çağıranlar aynı sözü versin). */
export const EMERGENCY_STOP_UNCONFIRMED_TITLE = "⚠️ ACİL DURDURMA DOĞRULANAMADI";
export const EMERGENCY_STOP_UNCONFIRMED_BODY =
  "Donanımın durduğu teyit edilemedi. Bobinler hâlâ çalışıyor olabilir — cihazı fiziksel güç düğmesinden kapatın.";
