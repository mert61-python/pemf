// Author: mertaygn, cglrgrkn
/**
 * AYARLAR → HESAP BİLGİLERİ, PROFİLE GÖRE AYRIŞIR (2026-08-07, sahip bildirimi)
 *
 * ARIZA: Evcil hayvan sahibi modunda "Klinik / Muayenehane" ve "Klinik Acil Telefon"
 * gösteriliyordu; araştırma modunda ise kurum/bölüm alanı hiç yoktu.
 *
 * ⚠️ EN KRİTİK KURAL (veri kaybı): profil HER AÇILIŞTA seçilir ve kalıcı değildir → aynı
 * hesap bugün veteriner, yarın araştırmacı olabilir. Düzenleme formu TÜM alanları yüklemeli;
 * yalnız aktif profile ait olanları GÖSTERMELİ. Yüklemezse, araştırma modunda kaydeden bir
 * kullanıcının klinik bilgisi BOŞ gönderilip SİLİNİR.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { EN, TR, gorunenMetinler } from "@/i18n/__tests__/kaynakMetni";

const SRC = readFileSync(join(__dirname, "..", "SettingsScreen.tsx"), "utf8");

/**
 * I18N-0: etiketler kataloğa taşındı — ölçüt GEVŞEMEDİ, yer değiştirdi (`kaynakMetni.ts`): yapısal koşul (isExpert / isResearcher)
 * ANAHTARIN kullanıldığı yerde aranır, anahtarın TR değeri eski metinle BİREBİR, EN değeri dolu olmalı.
 */
function etiket(anahtar: string, tr: string): string {
  expect(TR[anahtar]).toBe(tr);
  expect(String(EN[anahtar] ?? "").trim()).not.toBe("");
  return `t("${anahtar}")`;
}

/** `startEditProfile` gövdesini çıkarır (formun hangi alanları yüklediğini görmek için). */
function startEditBody(): string {
  const i = SRC.indexOf("const startEditProfile");
  expect(i).toBeGreaterThan(-1);
  return SRC.slice(i, SRC.indexOf("setEditP(true)", i));
}

describe("Ayarlar → hesap bilgileri profile göre ayrışır", () => {
  it("VETERİNER alanları isExpert ile koşullanır", () => {
    expect(SRC).toMatch(/isExpert && \(\s*<>\s*<Text style=\{styles\.label\}>\{t\("ayarlar\.hesap\.klinik"\)\}/);
    expect(SRC).toContain(etiket("ayarlar.hesap.klinik", "Klinik / Muayenehane")); // test İÇİNDE: kırmızı, çökme değil
  });

  it("ARAŞTIRMA alanları (kurum/bölüm) isResearcher ile koşullanır", () => {
    expect(SRC).toMatch(/isResearcher && \(/);
    expect(gorunenMetinler(SRC)).toContain("Üniversite / Kurum");
    expect(gorunenMetinler(SRC)).toContain("Bölüm / Anabilim Dalı");
  });

  it("klinik acil telefon da yalnız veterinerde sorulur", () => {
    const i = SRC.indexOf(etiket("ayarlar.hesap.klinikAcilTelefon", "Klinik Acil Telefon"));
    expect(i).toBeGreaterThan(-1);
    const once = SRC.slice(Math.max(0, i - 260), i);
    expect(once).toContain("isExpert");
  });

  it("SALT-OKUNUR görünümde klinik bilgisi isExpert'e bağlı", () => {
    expect(SRC).toMatch(/isExpert && prof\.clinic_name/);
    expect(SRC).toMatch(/isExpert && prof\.clinic_phone/);
  });

  it("SALT-OKUNUR görünümde kurum bilgisi isResearcher'a bağlı", () => {
    expect(SRC).toMatch(/isResearcher && prof\.institution/);
    expect(SRC).toMatch(/isResearcher && prof\.department/);
  });

  // ── VERİ KAYBI KORUMASI ────────────────────────────────────────────────────
  it("düzenleme formu TÜM alanları yükler (gizli alanlar kaydederken SİLİNMEZ)", () => {
    const g = startEditBody();
    for (const alan of ["clinic_name", "clinic_phone", "institution", "department", "academic_title"]) {
      expect(g).toContain(`${alan}: prof.${alan}`);
    }
  });

  it("form başlangıç durumunda da tüm alanlar tanımlı (undefined gönderilmez)", () => {
    const i = SRC.indexOf("const [pForm, setPForm]");
    const blok = SRC.slice(i, SRC.indexOf("});", i));
    for (const alan of ["institution", "department", "academic_title"]) {
      expect(blok).toContain(alan);
    }
  });

  it("EV SAHİBİ için klinik ya da kurum alanı KOŞULSUZ render EDİLMEZ", () => {
    // Koşulsuz bir "Klinik / Muayenehane" etiketi kalmamalı — ev sahibi onu görürdü.
    const kosulsuz = SRC.match(/\n\s*<Text style=\{styles\.label\}>\{t\("ayarlar\.hesap\.klinik"\)\}<\/Text>/g) || [];
    expect(kosulsuz.length).toBeGreaterThan(0); // I18N-0: boş eşleşme kapıyı sessizce geçirmesin (anahtar değişirse KIRMIZI)
    for (const m of kosulsuz) {
      const idx = SRC.indexOf(m);
      expect(SRC.slice(Math.max(0, idx - 200), idx)).toContain("isExpert");
    }
  });
});
