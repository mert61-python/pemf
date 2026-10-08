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
 * KİMLİK İSTEMİ (D2.70 · Y103) — kimliksizken (cihazda kayıtlı operatör var, kimse seçili değil ya da kilit sonrası)
 * Hastalar, Seans Geçmişi ve AI Geçmişi kayıt göstermez, bunu söyler. TEK KAYNAK: ekranlar metni buradan alır.
 */
export const KIMLIK_ISTEMI = "Kayıtları görmek için operatörünüzü seçin";

/** A-61: hasta eklemek KİMLİK ister — kimliksiz eklenen hasta sahipsiz yazılır ve herkesin "Benim" listesine düşerdi. */
export const EKLEME_KIMLIK_ISTEMI = "Hasta eklemek için operatörünüzü seçin";

/**
 * "Benim" = operator_email eşleşen VEYA SAHİPSİZ kayıtlar (eski/migrasyon kayıtları kaybolmasın).
 *
 * ⚠️ D2.70 (B-6.19 · Y103): kimlik (`myEmail`) BOŞSA hiçbir kayıt kapsamda DEĞİLDİR — "Tüm Klinik" dahil (FAIL-CLOSED).
 * Eskiden "oturum e-postası yoksa filtre uygulanmaz" kuralıyla kimlik düşünce (açılış, kilit) ev sahibi kliniğin TÜM
 * hasta/seans/AI kayıtlarını "Benim" diye görüyordu (ölçüldü). Kimlik yalnız kayıtlı operatörlü cihazda boştur:
 * operatörü olmayan tek hekimli klinikte `operatorEmail` oturum e-postasıdır (Kural 2 — bugünkü gibi). Profil / "son
 * operatör" kalıcılığı EKLENMEZ. Kapı: __tests__/patientScope.test.ts + screens/__tests__/kimliksizKapsam.D270.Y103.web.
 */
export function inScope(
  hasta: { operator_email?: string | null },
  scope: PatientScope,
  myEmail: string,
): boolean {
  if (!myEmail) return false;
  if (scope === "all") return true;
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
  // ⚠️ D2.20 (A-10): "Tüm Klinik" silmesi de KİMLİK ister — kimliksiz (kayıtlı operatörlü cihaz, kimse seçili değil ya
  // da kilit sonrası) kliniğin tüm AI geçmişini silme isteği GİTMEZ (eskiden `izinli: true`; backend de artık 428 der).
  return { izinli: Boolean(mail), operatorEmail: "", allOperators: true };
}

/**
 * KAYIT SİLME YETKİSİ (D2.72 · B-6.26 · Y92) — hasta ve seans silmenin (toplu + tekil) TEK kaynağı.
 *
 * ⚠️ ÖLÇÜLEN KUSUR: toplu ve tekil silme kimlik/sahiplik sormadan ekranda görünen her kaydı isteğe koyuyordu →
 * "Tüm Klinik → Tümünü Seç → Sil" başka hekimlerin hasta ve SEANS kayıtlarını siliyor, araştırma profili kendisine
 * kapatılan "Tümünü Sil"i böyle dolanıyordu (DENETIM-06 B-6.26, İG-6.4).
 *
 * KURAL (sahip kararı Y92 — backend `servers/silme_yetkisi.py` AYNI kuralı jetondan uygular):
 *   * Kimlik yoksa → HİÇBİR kayıt (istek gitmez).
 *   * Cihazda kayıtlı operatör VARSA → yalnız `operator_email` = aktif operatör. SAHİPSİZ kayıt da "kendi" değildir
 *     ("Benim" listesinde GÖRÜNÜR ama silinmez — backend 403 der). "Tüm Klinik" görünümü bunu değiştirmez.
 *   * Operatörsüz tek hekimli klinik (Kural 2) → bugünkü gibi her kayıt; YALNIZ araştırma profili "Tüm Klinik"te kendi
 *     kayıtlarıyla sınırlı (B-6.26 — "Tümünü Sil" ona kapalı; bu kol yalnız arayüzde: backend profili bilmez).
 */
export function silinebilir(
  kayit: { operator_email?: string | null },
  b: { myEmail: string; operatorKayitli: boolean; kapsam: PatientScope; isExpert: boolean },
): boolean {
  const mail = (b.myEmail || "").trim().toLowerCase();
  if (!mail) return false;
  const sahip = (kayit.operator_email || "").trim().toLowerCase();
  if (b.operatorKayitli) return sahip === mail;
  if (b.kapsam === "all" && !b.isExpert) return sahip === mail;
  return true;
}

/** Tekil silmede kayıt kimliğe ait değilse (ya da toplu seçimin HİÇBİRİ silinemiyorsa) gösterilen metin. */
export const YALNIZ_KENDI_SILME = "Yalnız kendi kayıtlarınızı silebilirsiniz — bu kayıt başka bir hekime ait ya da sahipsiz.";

/** Kimlik yokken silme denemesi (kayıtlı operatörlü cihaz, kimse seçili değil ya da kilit sonrası). */
export const SILME_KIMLIK_ISTEMI = "Silmek için operatörünüzü seçin";

/** Toplu silme onayında, seçimden silinmeyecek kayıtların sayısı. */
export function silinmeyecekNotu(n: number): string {
  return n > 0 ? `\n\n${n} kayıt başka bir hekime ait ya da sahipsiz — SİLİNMEYECEK.` : "";
}
