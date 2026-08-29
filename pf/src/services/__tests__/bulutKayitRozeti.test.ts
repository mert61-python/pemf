// Author: mertaygn, cglrgrkn
/**
 * BULUT KAYIT ROZETİ — sessiz uzaktan-erişim arızasının ekrandaki karşılığı.
 *
 * DENETİM 2026-08-28 #02. Bu makinede CANLI ölçüldü: `/api/health` → `cloudRegistry:
 * "secret_mismatch"`, cihaz açık, internete bağlı, eşleştirme kodu üretiliyor — ama bulut
 * kaydı 13 gündür güncellenmiyor, `tunnel_url` NULL. Backend bu alanı TAM BU AMAÇLA
 * yayınlıyordu; `pf/` altında onu okuyan tek bir üretim dosyası yoktu.
 *
 * Kök neden kalıcı bir ASİMETRİ: `device_id` MAC adresinden türetildiği için yeniden
 * kurulumda AYNI gelir, `device_registry_secret` ise rastgele üretilip yalnız
 * `pemf_secrets.json`da yaşadığı için DEĞİŞİR. Buluttaki TOFU mührü eski sırra bağlı →
 * yazma kalıcı olarak reddedilir.
 *
 * ⚠️ "ok"/"unknown"da rozet ÇİZİLMEZ: Supabase hiç yapılandırılmamış klinikte uyarı
 * göstermek yanlış alarmdır. Yanlış teşhis, teşhissizlikten kötüdür.
 */
import { bulutKayitRozeti, eslestirmeKoduUzaktanGecerliMi } from "@/services/bulutKayit";

describe("bulutKayitRozeti", () => {
  it("KRİTİK: secret_mismatch HATA seviyesinde ve kodun çalışmayacağını söyler", () => {
    const r = bulutKayitRozeti("secret_mismatch");
    expect(r).not.toBeNull();
    expect(r!.seviye).toBe("hata");
    expect(r!.metin).toMatch(/uzaktan/i);
    // Operatör "kod ekranda var ama işe yaramıyor" gerçeğini okuyabilmeli.
    expect(r!.metin).toMatch(/ÇALIŞMAZ|çalışmaz/);
    // Yerel ağın etkilenmediği de söylenmeli — gereksiz panik olmasın.
    expect(r!.metin).toMatch(/aynı ağ/i);
  });

  it("KRİTİK: sağlıklı durumda rozet ÇİZİLMEZ (yanlış alarm yok)", () => {
    expect(bulutKayitRozeti("ok")).toBeNull();
  });

  it("KRİTİK: bulut hiç yapılandırılmamışsa (unknown) rozet ÇİZİLMEZ", () => {
    expect(bulutKayitRozeti("unknown")).toBeNull();
    expect(bulutKayitRozeti(undefined)).toBeNull();
    expect(bulutKayitRozeti(null)).toBeNull();
    expect(bulutKayitRozeti("")).toBeNull();
  });

  it("rpc_missing ve error UYARI seviyesinde bildirilir", () => {
    for (const d of ["rpc_missing", "error", "istemci_yok"]) {
      const r = bulutKayitRozeti(d);
      expect(r).not.toBeNull();
      expect(r!.seviye).toBe("uyari");
      expect(r!.metin.length).toBeGreaterThan(30);
    }
  });

  it("bilinmeyen bir durum sessizce yutulur (ileri uyumluluk)", () => {
    expect(bulutKayitRozeti("gelecekte_eklenen_durum")).toBeNull();
  });
});

describe("eslestirmeKoduUzaktanGecerliMi", () => {
  it("KRİTİK: kod buluta gitmiyorsa GEÇERSİZ sayılır", () => {
    expect(eslestirmeKoduUzaktanGecerliMi("secret_mismatch")).toBe(false);
    expect(eslestirmeKoduUzaktanGecerliMi("rpc_missing")).toBe(false);
  });

  it("sağlıklı ve bilinmeyen durumda kod geçerli sayılır (yanlış negatif üretme)", () => {
    expect(eslestirmeKoduUzaktanGecerliMi("ok")).toBe(true);
    expect(eslestirmeKoduUzaktanGecerliMi("unknown")).toBe(true);
    // Geçici ağ hatası kodu geçersiz KILMAZ — kayıt eski olabilir ama sır doğrudur.
    expect(eslestirmeKoduUzaktanGecerliMi("error")).toBe(true);
  });
});
