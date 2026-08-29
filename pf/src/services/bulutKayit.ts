// Author: mertaygn, cglrgrkn
/**
 * Bulut cihaz-kaydı (device registry) durumunun operatöre gösterilecek karşılığı.
 *
 * DENETİM 2026-08-28 #02. Backend `/api/health` içinde `cloudRegistry` alanını TAM BU AMAÇLA
 * yayınlıyordu — ama `pf/` altında onu okuyan tek bir üretim dosyası yoktu (yalnız bir test
 * yorumunda geçiyordu). Sonuç: cihazın bulut kaydı 13 gündür güncellenmiyorken ekran hiçbir
 * şey söylemiyor, hatta eşleştirme kodunu koşulsuz "bu cihazın kodu" diye sunuyordu. Kod
 * ekranda görünüyor ama buluta gitmediği için uzaktan bağlanmak ÇALIŞMIYOR.
 *
 * ⚠️ "secret_mismatch" KALICIDIR: cihaz kimliği (device_id) MAC adresinden türediği için
 * yeniden kurulumda AYNI kalır, ama `device_registry_secret` rastgele üretilip yalnız
 * `pemf_secrets.json`da yaşadığı için veri kökü yenilenince DEĞİŞİR. Buluttaki TOFU mührü
 * (upsert_device_envanter.sql) eski sırra bağlı olduğundan yazma kalıcı olarak reddedilir.
 *
 * ⚠️ "ok" ve "unknown" durumlarında rozet ÇİZİLMEZ (null döner): Supabase hiç yapılandırılmamış
 * bir klinikte uyarı göstermek yanlış alarmdır — yanlış teşhis, teşhissizlikten kötüdür.
 */

export type BulutKayitRozeti = {
  seviye: "uyari" | "hata";
  metin: string;
};

/** `/api/health` → `cloudRegistry` değerini tek cümleye çevirir. null → rozet gösterilmez. */
export function bulutKayitRozeti(durum: string | null | undefined): BulutKayitRozeti | null {
  switch (durum) {
    case "secret_mismatch":
      return {
        seviye: "hata",
        metin:
          "Uzaktan erişim güncellenmiyor: bu cihazın kimliği bulutta başka bir güvenlik " +
          "anahtarıyla kayıtlı (genellikle yeniden kurulum sonrası olur). Aşağıdaki " +
          "eşleştirme kodu uzaktan bağlanmak için ÇALIŞMAZ. Aynı ağdaki bağlantı etkilenmez. " +
          "Destek ekibinden cihazın bulut kaydının sıfırlanmasını isteyin.",
      };
    case "rpc_missing":
      return {
        seviye: "uyari",
        metin:
          "Bulut kaydı eksik yapılandırmayla yazılıyor: eşleştirme kodu buluta gönderilmiyor, " +
          "bu yüzden kodla uzaktan bağlanma çalışmaz. Aynı ağdaki bağlantı etkilenmez.",
      };
    case "error":
      return {
        seviye: "uyari",
        metin:
          "Cihazın bulut kaydı şu an güncellenemiyor (ağ ya da sunucu hatası). Uzaktan " +
          "erişim bilgileri eskimiş olabilir; sorun sürerse destek ekibine bildirin.",
      };
    case "istemci_yok":
      return {
        seviye: "uyari",
        metin:
          "Bulut bağlantısı kurulmadı: cihaz uzaktan erişim için kayıt olmuyor. " +
          "Aynı ağdaki bağlantı etkilenmez.",
      };
    default:
      // "ok" → sağlıklı; "unknown" → bulut hiç yapılandırılmamış olabilir. İkisinde de sus.
      return null;
  }
}

/** Eşleştirme kodunun uzaktan bağlanmak için GEÇERLİ olup olmadığı. */
export function eslestirmeKoduUzaktanGecerliMi(durum: string | null | undefined): boolean {
  return durum !== "secret_mismatch" && durum !== "rpc_missing";
}
