// Author: mertaygn, cglrgrkn
/**
 * emergencyStop — donanım acil durdurmanın TEK KAYNAĞI.
 * ======================================================
 * Eskiden bu mantık yalnız `useSessionControl` içindeydi. Sorun: acil durdurmayı çağırması gereken
 * her yer (çıkış yap, profil değiştir, kabuk-seviyesi E-stop) o hook'u mount etmek zorunda kalıyordu;
 * hook ise mount'ta `/session/active` çekip 2sn'lik mutabakat interval'i kuruyor → her tüketici
 * fazladan bir poll döngüsü demek. Mantık buraya alındı: hook'suz, yan-etkisiz, her yerden çağrılabilir.
 *
 * Üç adım:
 *   1) Bridge ucu  POST /api/hardware/emergency_stop  → STM + ESP tek seferde durdurulur.
 *   2) Yedek       aynı yetkili uç standart istemciyle (farklı taşıma yolu)
 *   3) Son çare    POST /api/session/stop + /api/hardware/command{stop_all_coils}
 * ⚠️ D1.105 · A-63 (sahip): 2. ve 3. adım teyitten BAĞIMSIZ, HER ZAMAN koşar — gönderim AZALTILAMAZ (Ö.4-Y8). Eskiden
 * 1. adım teyitliyse erken dönülüyordu (zincir C1-13); ESP kapalıyken teyit artık STM'e bağlı olduğu için bu, her
 * başarılı basışta yedek STOP'ların kaybı demekti. Teyit = 1. VEYA 2. adımın backend teyidi; 3. adım teyit vermez.
 * Hiçbiri teyit veremezse `confirmed:false` döner ve ÇAĞIRAN kullanıcıyı "fiziksel güç düğmesi" uyarısıyla
 * bilgilendirmek ZORUNDADIR.
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
  /** TD3: kartın bu STOP'a yanıtı — "red" = STM_NACK (kabul yok) → teyit YOK, eylem: gücü kes / USB'yi çıkar.
   *  T2D-1: "yanitsiz" = STOP'a hiç yanıt yok → `confirmed:false`; ekranda genel "teyit edilemedi" uyarısı (fiziksel güç). */
  stmKartYaniti?: "kabul" | "red" | "yanitsiz" | null;
  stmRedMesaji?: string | null;
  /** Y227 (BE 2b): durdurma ANINDA bobin / seans var mıydı (false = boştaydı, null = okunamadı). Eski backend göndermez. */
  calisiyordu?: boolean | null;
}
interface CommandResponse {
  status?: string;
}

/** Bridge ucunun zaman aşımı. Yedek yol apiPost'un kendi 8sn'lik timeout'unu kullanır. */
const BRIDGE_TIMEOUT_MS = 5000;

/**
 * Donanımı durdur. ASLA throw etmez.
 * @returns `confirmed` — donanımın durduğu SUNUCU TARAFINDAN teyit edildi mi.
 *          `false` ise bobinler hâlâ çalışıyor OLABİLİR; çağıran mutlaka uyarmalıdır (`kartReddetti` → KART_RED metni).
 *          `kartReddetti` — TD3: teyit yok VE kart STOP'u NACK'ledi (backend `stmKartYaniti: "red"`).
 *          `calisiyordu` — Y227: durdurma ANINDA bir şey çalışıyor muydu (yanıtlardan biri `true` ise true; okunamadıysa null;
 *          hiçbir yanıt alanı taşımıyorsa undefined → çağıran eski davranışı korur). Yalnız GÖRÜNÜRLÜK — gönderimi etkilemez.
 */
export async function performEmergencyStop(): Promise<{
  confirmed: boolean;
  kartReddetti: boolean;
  calisiyordu?: boolean | null;
}> {
  let teyitli = false;
  let kartRed = false;
  // Aynı basış İKİ E-stop isteği gönderir (1. ve 2. adım); ikincisi bobinleri zaten durmuş görür → herhangi biri "çalışıyordu" derse o.
  let calisiyordu: boolean | null | undefined = undefined;
  const calismaBilgisi = (r: EmergencyStopResponse | null) => {
    if (!r || !("calisiyordu" in r)) return;
    const c = r.calisiyordu;
    if (c === true || calisiyordu === true) calisiyordu = true;
    else if (c !== false || calisiyordu === null) calisiyordu = null;
    else calisiyordu = false;
  };
  // ⚠️ SGI-3.2 (A-63 · 1-C i3-F-5 · Ö.4-Y8 — gecikme de kapılanmadır): TD3'ten beri backend E-stop yanıtı, STOP porta yazıldıktan
  // SONRA kartın yanıtını ≤ 0,25 sn bekliyor (NACK'li / yanıtsız kartta tam süre). Adımlar sırayla `await` edildiğinde 2. adım ve
  // `stop_all_coils` bu RAPOR beklemesi kadar (×2) GEÇ gidiyordu. Yedek STOP'lar artık 1. adımın yanıtını BEKLEMEDEN gider;
  // `/session/stop` 1./2. adımdan SONRA kalır (seans kaydı "acil-durdurma" olarak kapanır — E-stop ile yarışmaz).
  const adim1 = adim1Bridge();
  const adim2 = (async () => {
    try {
      const r = await apiPost<EmergencyStopResponse | null>(
        "/hardware/emergency_stop", {}, null, { silent: true, durdurma: true }); // D3I-A1.3 · Y8: düz-HTTP kapısına bağlanmaz
      if (r?.confirmed === true) teyitli = true;
      if (r?.stmKartYaniti === "red") kartRed = true;
      calismaBilgisi(r);
    } catch {
      /* aşağıdaki son çareye düş */
    }
  })();
  const stopAll = (async () => {
    try {
      await apiPost<CommandResponse | null>(
        "/hardware/command",
        { command: "stop_all_coils", params: {} },
        null,
        { silent: true, durdurma: true }
      );
    } catch {
      /* yut — teyit 1./2. adımdan gelir */
    }
  })();
  const d1 = await adim1;
  if (d1?.confirmed === true) teyitli = true;
  if (d1?.stmKartYaniti === "red") kartRed = true;
  calismaBilgisi(d1);

  // 2) Yedek: AYNI yetkili uç standart istemciyle (yukarıda, 1. adımla AYNI anda başladı). Birincil yol ham `fetch` + bridge
  // adresini kullanır; bu ise apiPost'un taban adresi/auth'u/timeout'u üzerinden gider (tünel
  // dahil) → gerçekten FARKLI bir taşıma yolu, ama teyit yine tek ve doğru kaynaktan gelir.
  await adim2;

  // 3) Son çare: seansı kapat + STM'e STOP (`stop_all_coils` yukarıda HEMEN gitti) — 1./2. adım teyitli olsa da GÖNDERİLİR
  // (A-63). ⚠️ Bu yol ESP'yi KAPSAMAZ ve porta yazımı teyit etmez: kendi başına `confirmed` VERMEZ. Eskiden burada
  // `status === "success"` teyit sayılıyordu — STM'in durması, ESP bobinleri hastanın üzerinde çalışırken "hepsi kesildi" diye
  // raporlanıyordu.
  try {
    await apiPost<CommandResponse | null>("/session/stop", {}, null, { silent: true, durdurma: true });
  } catch {
    /* yut — teyit 1./2. adımdan gelir */
  }
  await stopAll;
  return { confirmed: teyitli, kartReddetti: !teyitli && kartRed, calisiyordu };
}

/** 1. adım: bridge ucu (tek atışta STM + ESP). ASLA throw etmez; gövde yoksa / okunamazsa null. */
async function adim1Bridge(): Promise<EmergencyStopResponse | null> {
  // 1) Bridge (tek atışta STM + ESP).
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), BRIDGE_TIMEOUT_MS);
    try {
      const response = await fetch(`${serviceConfig.bridgeBaseUrl}/hardware/emergency_stop`, {
        method: "POST",
        // GÜVENLİK/GECİKME: eskiden yalnız Content-Type gönderiliyordu. Uzaktan (tünel) erişimde
        // backend auth'u ZORUNLU kıldığından bu istek HER SEFERİNDE 401 alıyor, birincil yol
        // boşuna harcanıyor ve acil durdurma ancak yedek yoldan (saniyeler sonra) gerçekleşiyordu.
        headers: { "Content-Type": "application/json", ...authHeaders() },
        signal: ctrl.signal,
      });
      if (!response.ok) throw new Error(`emergency_stop HTTP ${response.status}`);
      // ⚠️ GÖVDE OKUMASI DA ZAMAN AŞIMININ İÇİNDE (denetim 2026-08-17). `clearTimeout` eskiden
      // yalnız `fetch`i saran iç `finally`deydi; `response.json()` o noktadan sonra çalıştığı için
      // AbortController'a BAĞLI DEĞİLDİ ve gövde asılırsa `performEmergencyStop` 1500 ms içinde
      // dönmüyordu (ölçüldü: 1501 ms). Doğru desen `apiClient.ts`te zaten kurulmuş.
      // Davranış eşdeğerliği: abort'ta `json()` reddeder, mevcut `.catch(() => null)` yutar →
      // `data = null` → bugünkü "2xx ama teyit yok" yoluyla AYNI şekilde yedek yola düşülür.
      const data = (await response.json().catch(() => null)) as EmergencyStopResponse | null;
    // ⚠️ DENETİM 2026-08-09 (ENGEL) — HASTA GÜVENLİĞİ: teyit ARTIK backend'den okunuyor.
    // Eski hâli `stmStopped VEYA herhangi-bir-bobin-success` idi. Bu bir VEYA olduğu için:
    // STM durup 3 ESP bobininin ÜÇÜ birden başarısız olsa bile — ya da 8 bobinden yalnız 1'i
    // onaylansa bile — arayüz "durduruldu" diyordu. Backend AYNI yanıtta doğru cevabı
    // (`confirmed` = tüm transport'lar) zaten gönderiyordu; istemci onu yok sayıp kendi
    // gevşek kuralını uyguluyordu. Bir bobin hastanın üzerinde çalışmaya devam ederken
    // operatöre "kesildi" demek, bu ekrandaki en ağır hata sınıfıdır.
      // ⚠️ D1.105 · A-63: teyitli olsa da ERKEN DÖNÜLMEZ — 2. ve 3. adım koşulsuz (Ö.4-Y8).
      return data;
    } finally {
      clearTimeout(timer);
    }
  } catch {
    /* bridge erişilemedi → yedek yol */
    return null;
  }
}

/**
 * Teyit edilemeyen durdurma için ORTAK uyarı metni (tüm çağıranlar aynı sözü versin) — I18N: metin artık katalogda ve çeviri sisteminden BAĞIMSIZ
 * (`kritikMetin("guvenlik.acilDurdur.teyitsizBaslik" | "…teyitsizGovde")`, `i18n/kritik.ts` KRITIK_YEDEK); çağıranlar (useSessionControl,
 * useTeardownGuard) doğrudan onu kullanır.
 */

/**
 * TD3 (tezgâh Oturum 13): kart STOP'u REDDETTİ (STM_NACK). Backend `utils/stm32_kimlik.ESTOP_KART_RED_METNI` ile AYNI metin
 * (eşlik: tests/test_TD3_estop_kartin_STOP_NACKi_teyit_DEGILDIR.py). Eylem söyler: gücü kes / USB'yi çıkar.
 */
// I18N: `kritikMetin("guvenlik.acilDurdur.kartRedBaslik" | "…kartRedGovde")` (yukarıdaki not).
