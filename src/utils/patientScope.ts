// Author: mertaygn, cglrgrkn
/**
 * HASTA KAPSAMI (KVKK kapısı) — 2026-08-08
 *
 * Hasta veritabanı aynı makinede ÜÇ PROFİL ARASINDA PAYLAŞILIR. "Hastalar" ekranı bu tarihte
 * ev sahibi (pet_owner) profiline de açıldı (AI analizi hasta seçimi zorunlu kıldığı için) →
 * ev sahibi "Tüm Klinik" sekmesine basıp kliniğin tüm hasta listesini (sahip adı, iletişim =
 * kişisel veri) görebilecekti. Bu modül kapsamı TEK YERDEN belirler; ekran yalnız onu uygular.
 *
 * KURAL: ev sahibi HER ZAMAN "mine" — sekme gizlenmiş olsa bile mantık burada kilitli.
 */
export type PatientScope = "mine" | "all";

/** Sekme gizli olsa da geçerli kapsam: klinik profilleri seçebilir, ev sahibi seçemez. */
export function effectiveScope(
  istenen: PatientScope,
  { isExpert, isResearcher }: { isExpert: boolean; isResearcher: boolean },
): PatientScope {
  return isExpert || isResearcher ? istenen : "mine";
}

/** Kapsam sekmesi gösterilsin mi (oturum yoksa sahiplik bilinmez → gösterilmez). */
export function canChooseScope(
  myEmail: string,
  roles: { isExpert: boolean; isResearcher: boolean },
): boolean {
  return Boolean(myEmail) && (roles.isExpert || roles.isResearcher);
}

/**
 * "Benim" = operator_email eşleşen VEYA SAHİPSİZ kayıtlar (eski/migrasyon kayıtları kaybolmasın).
 * Oturum e-postası yoksa sahiplik kıyaslanamaz → filtre uygulanmaz (mevcut davranış korunur).
 */
export function inScope(
  hasta: { operator_email?: string | null },
  scope: PatientScope,
  myEmail: string,
): boolean {
  if (scope === "all" || !myEmail) return true;
  const op = (hasta.operator_email || "").toLowerCase();
  return !op || op === myEmail;
}

/**
 * SİLME KAPSAMI (2026-08-09 denetimi, Tier 1) — yıkıcı işlemin TEK kaynağı.
 *
 * ⚠️ NEDEN AYRI BİR FONKSİYON: bu denetimde bulunan arıza, aynı kuralın üç ekranda ayrı ayrı
 * yazılmış olmasıydı ve `AiHistoryScreen` kimliği `session.email`den (paylaşılan giriş hesabı)
 * alıyordu. Backend'de kapsam `operator_email`e bağlıdır ve BOŞ e-posta "sahip filtresi yok"
 * demektir; yani kimliğin kaybolduğu her durum sessizce KLİNİĞİN TÜM GEÇMİŞİNİ silmeye
 * dönüşüyordu. Karar tek yerde olsun ki bir daha ayrışmasın.
 *
 * Dönen:
 *   izinli=false → çağırma; kullanıcıdan operatör seçmesini iste (kimlik yok, kapsam "benim")
 *   operatorEmail → backend'e gidecek sahip filtresi ("" yalnız klinik-geneli silmede)
 *   allOperators  → klinik-geneli silme NİYETİ (backend fail-closed bunu şart koşar)
 */
export interface SilmeKapsami {
  izinli: boolean;
  operatorEmail: string;
  allOperators: boolean;
}

export function deleteScope(
  scope: PatientScope,
  operatorEmail: string,
  roles: { isExpert: boolean; isResearcher: boolean },
): SilmeKapsami {
  const etkin = effectiveScope(scope, roles);
  // Klinik profili DEĞİLSE (ev sahibi) kapsam her zaman "benim" — sekme gizli olsa da.
  const kendi = etkin === "mine" || !(roles.isExpert || roles.isResearcher);
  const mail = (operatorEmail || "").trim().toLowerCase();
  if (kendi) {
    // Kimlik yoksa İSTEK GÖNDERİLMEZ. Boş e-posta göndermek "hepsini sil" demektir.
    return { izinli: Boolean(mail), operatorEmail: mail, allOperators: false };
  }
  return { izinli: true, operatorEmail: "", allOperators: true };
}
