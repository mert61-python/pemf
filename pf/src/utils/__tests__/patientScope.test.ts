// Author: mertaygn, cglrgrkn
/**
 * KVKK KAPISI — ev sahibi kliniğin hasta listesini GÖREMEZ (2026-08-08)
 *
 * BAĞLAM: "Hastalar" ekranı bu tarihte pet_owner profiline açıldı (AI analizi hasta seçimi
 * zorunlu kıldığı için). Hasta DB'si aynı makinede üç profil arasında PAYLAŞILDIĞINDAN, ekranın
 * "Tüm Klinik" sekmesi ev sahibine kliniğin tüm kayıtlarını (sahip adı/iletişim = kişisel veri)
 * açardı. Bu testler kapının İKİ katmanını da kanıtlar: sekme gizli VE mantık kilitli.
 */
import { canChooseScope, deleteScope, effectiveScope, inScope } from "@/utils/patientScope";

const VET = { isExpert: true, isResearcher: false };
const ARASTIRMA = { isExpert: false, isResearcher: true };
const EV_SAHIBI = { isExpert: false, isResearcher: false };

describe("effectiveScope — ev sahibi 'all' kapsamına çıkamaz", () => {
  it("KRİTİK: ev sahibi 'all' istese bile 'mine' döner", () => {
    expect(effectiveScope("all", EV_SAHIBI)).toBe("mine");
  });

  it("veteriner ve araştırmacı 'all' seçebilir", () => {
    expect(effectiveScope("all", VET)).toBe("all");
    expect(effectiveScope("all", ARASTIRMA)).toBe("all");
  });

  it("'mine' her profilde 'mine' kalır", () => {
    for (const r of [VET, ARASTIRMA, EV_SAHIBI]) expect(effectiveScope("mine", r)).toBe("mine");
  });
});

describe("canChooseScope — kapsam sekmesi görünürlüğü", () => {
  it("ev sahibine sekme GÖSTERİLMEZ (oturumu olsa bile)", () => {
    expect(canChooseScope("ali@example.com", EV_SAHIBI)).toBe(false);
  });

  it("klinik profillerine oturum varsa gösterilir", () => {
    expect(canChooseScope("vet@example.com", VET)).toBe(true);
    expect(canChooseScope("arastirma@example.com", ARASTIRMA)).toBe(true);
  });

  it("oturum yoksa hiç kimseye gösterilmez (sahiplik kıyaslanamaz)", () => {
    expect(canChooseScope("", VET)).toBe(false);
  });
});

describe("SÖZLEŞME: kapıyı kullanan TÜM ekranlar", () => {
  // Aynı hata İKİ KEZ oldu: kapı önce PatientScreen'de, sonra AiHistoryScreen'de eksikti
  // (ikisi de yalnız `myEmail`e bakıyordu, PROFİLE değil). Bu test, kuralı kullanan ekranların
  // gerçekten TEK KAYNAĞI çağırdığını kaynak metninden doğrular — üçüncü kez ayrışmasın.
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const EKRANLAR = ["PatientScreen.tsx", "AiHistoryScreen.tsx"];

  it.each(EKRANLAR)("%s tek kaynağı kullanır (elle myEmail kontrolü DEĞİL)", (dosya) => {
    const src = fs.readFileSync(path.join(__dirname, "..", "..", "screens", dosya), "utf8");
    expect(src).toContain("canChooseScope");
    expect(src).toContain("effectiveScope");
    // Kapsam sekmesi doğrudan `myEmail ?` ile koşullanmamalı — profil kontrolünü atlar.
    expect(src).not.toMatch(/\{\s*myEmail\s*\?\s*\(/);
  });
});

describe("inScope — sahiplik filtresi", () => {
  const BENIM = { operator_email: "vet@example.com" };
  const BASKASI = { operator_email: "baska@example.com" };
  const SAHIPSIZ = { operator_email: "" };

  it("KRİTİK: ev sahibinin geçerli kapsamında BAŞKASININ hastası GÖRÜNMEZ", () => {
    const scope = effectiveScope("all", EV_SAHIBI);   // kullanıcı "all" zorlasa bile
    expect(inScope(BASKASI, scope, "sahip@example.com")).toBe(false);
  });

  it("kendi kaydını görür", () => {
    expect(inScope(BENIM, "mine", "vet@example.com")).toBe(true);
  });

  it("SAHİPSİZ (eski/migrasyon) kayıtlar kaybolmaz", () => {
    expect(inScope(SAHIPSIZ, "mine", "vet@example.com")).toBe(true);
    expect(inScope({}, "mine", "vet@example.com")).toBe(true);
  });

  it("'all' kapsamında (klinik profili) başkasının kaydı görünür", () => {
    expect(inScope(BASKASI, effectiveScope("all", VET), "vet@example.com")).toBe(true);
  });

  it("e-posta büyük/küçük harf farkı sahipliği bozmaz", () => {
    expect(inScope({ operator_email: "VET@Example.com" }, "mine", "vet@example.com")).toBe(true);
  });

  it("oturum e-postası yoksa filtre uygulanmaz (mevcut davranış korunur)", () => {
    expect(inScope(BASKASI, "mine", "")).toBe(true);
  });
});

describe("SÖZLEŞME: operatör e-postası AKTİF OPERATÖRDEN gelir", () => {
  // 2026-08-08: tek makineyi 3-4 veteriner paylaşıyor. Kayıt yazan yollar oturum e-postasını
  // KULLANMAMALI — yoksa herkesin kaydı aynı kişiye yazılır ve "Benim Hastalarım" ayrımı
  // (bu dosyanın koruduğu şey) anlamsız kalır.
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  // ⚠️ 2026-08-09 (Tier 1): liste EKSİKTİ — yalnız kayıt YAZAN üç yolu kapsıyordu. Oysa kaydı
  // OKUYAN/SİLEN/FİLTRELEYEN ekranlar da aynı kimliği kullanmak zorunda ve onlar
  // `session?.email` kullanıyordu. Kapı onları görmediği için arıza sessizce yaşadı:
  //   • AiHistoryScreen      → "kendi kayıtlarımı sil" BAŞKA hekimin analizlerini siliyordu
  //   • PatientScreen        → yeni hasta paylaşılan giriş hesabına damgalanıyordu
  //   • TreatmentHistoryScreen → "Benim Seanslarım" filtresi yanlış kişiye bakıyordu
  // Kimliği kullanan HER ekran bu listede olmalı.
  const YAZAN = [
    ["screens", "ControlScreen.tsx"],
    ["screens", "AiHubScreen.tsx"],
    ["components", "domain", "AiProPanel.tsx"],
    ["screens", "AiHistoryScreen.tsx"],
    ["screens", "PatientScreen.tsx"],
    ["screens", "TreatmentHistoryScreen.tsx"],
  ];

  it.each(YAZAN)("%s/%s aktif operatörü kullanır", (...parcalar) => {
    const src = fs.readFileSync(path.join(__dirname, "..", "..", ...parcalar), "utf8");
    expect(src).toContain("useOperator");
    // `operator_email`/`operatorEmail` doğrudan oturum e-postasından beslenmemeli.
    expect(src).not.toMatch(/operatorEmail\s*[:=]\s*session\?\.email/);
    expect(src).not.toMatch(/operator_email:\s*session\?\.email/);
    // ⚠️ 2026-08-09: kimliği tutan yerel değişken de oturumdan BESLENMEMELİ. Asıl arıza tam
    // buydu: `const myEmail = (session?.email || "").toLowerCase()` → paylaşılan giriş hesabı.
    expect(src).not.toMatch(/myEmail\s*=\s*\(?session\?\.email/);
  });
});

/**
 * SİLME KAPSAMI (2026-08-09 denetimi, Tier 1) — yıkıcı işlemin tek kaynağı.
 *
 * ARIZA: aynı kural üç ekranda ayrı ayrı yazılmıştı ve `AiHistoryScreen` kimliği
 * `session.email`den (paylaşılan Supabase giriş hesabı) alıyordu, aktif operatörden değil.
 * Backend'de kapsam `operator_email`e bağlıdır ve BOŞ e-posta "sahip filtresi yok" demektir —
 * yani kimliğin kaybolduğu her durum sessizce KLİNİĞİN TÜM AI GEÇMİŞİNİ silmeye dönüşüyordu.
 */
// VET / ARASTIRMA / EV_SAHIBI sabitleri dosyanın başında zaten tanımlı — yeniden tanımlama.
describe("deleteScope", () => {
  it("KRİTİK: kimlik YOKSA istek gönderilmez (boş e-posta 'hepsini sil' demektir)", () => {
    const r = deleteScope("mine", "", VET);
    expect(r.izinli).toBe(false);
    expect(r.allOperators).toBe(false);
  });

  it("KRİTİK: kimliksiz ev sahibi ASLA klinik-geneli silemez", () => {
    // Ev sahibi için kapsam her zaman "mine"; "all" seçse bile.
    const r = deleteScope("all", "", EV_SAHIBI);
    expect(r.izinli).toBe(false);
    expect(r.allOperators).toBe(false);
  });

  it("kendi kayıtları: e-posta gider, klinik bayrağı KAPALI", () => {
    expect(deleteScope("mine", "Dr.A@Klinik.com", VET)).toEqual({
      izinli: true, operatorEmail: "dr.a@klinik.com", allOperators: false,
    });
  });

  it("klinik profili 'Tüm Klinik' seçerse bayrak AÇIK, e-posta boş", () => {
    expect(deleteScope("all", "dr.a@klinik.com", VET)).toEqual({
      izinli: true, operatorEmail: "", allOperators: true,
    });
    expect(deleteScope("all", "x@y.com", ARASTIRMA).allOperators).toBe(true);
  });

  it("KRİTİK: ev sahibi 'all' seçse bile KENDİ kapsamında kalır", () => {
    const r = deleteScope("all", "sahip@x.com", EV_SAHIBI);
    expect(r.allOperators).toBe(false);
    expect(r.operatorEmail).toBe("sahip@x.com");
  });

  it("e-posta normalize edilir (büyük harf / boşluk backend eşleşmesini bozmasın)", () => {
    expect(deleteScope("mine", "  Dr.A@Klinik.COM  ", VET).operatorEmail).toBe("dr.a@klinik.com");
  });

  it("yalnız boşluktan ibaret e-posta KİMLİK SAYILMAZ", () => {
    expect(deleteScope("mine", "   ", VET).izinli).toBe(false);
  });
});
