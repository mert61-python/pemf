// Author: mertaygn, cglrgrkn
/**
 * TÜRKÇE ARAMA — `İ`/`I` ile yazılan kayıt bulunabilmeli.
 *
 * DENETİM BULGUSU (2026-08-17). Üç arama filtresi de `toLowerCase()` kullanıyordu ve depoda
 * `toLocaleLowerCase` HİÇ geçmiyordu:
 *     src/screens/PatientScreen.tsx · src/screens/TreatmentHistoryScreen.tsx
 *     src/components/domain/PatientGate.tsx
 *
 * `node -e` ile ölçüldü:
 *     "İpek".toLowerCase() === "i̇pek"   (5 kod noktası: 'i' + U+0307 COMBINING DOT ABOVE)
 *     "i̇pek".includes("ipek")           → false
 *     'IŞIK'.toLowerCase() === "işik"  ≠  'Işık'.toLowerCase() === "işık"  → false
 *
 * En ağır etki `TreatmentHistoryScreen`: süzme YALNIZ yüklenmiş sayfalar üzerinde olduğu için
 * aramaya güvenen hekim "bu hastanın geçmişi yok" sonucuna varır; PDF/CSV dışa aktarımı da
 * `filteredSessions` üzerinden gittiği için **boş/eksik rapor** üretir.
 *
 * ⚠️ Backend'de telafi YOK: `servers/patient_router.py`'de arama ucu yoktur, istemci `/patients`ın
 * tamamını çekip yerelde süzer (Python `.lower()` de aynı U+0307'yi üretir).
 * ⚠️ Ekip locale'i biliyor ama aramaya taşımamış: `AiHistoryScreen` sıralamada
 * `localeCompare(a, b, "tr")` kullanıyor → bilinçli bir bırakma değil, taşınmamış bir düzeltme.
 * ⚠️ "Hasta ULAŞILAMAZ" DEĞİL: `PatientGate` arama boşken tam listeyi gösterip seçtiriyor
 * (testle kilitli) ve listeler kaydırılabilir. Kırık olan **arama kısayolu** ve **rapor içeriği**.
 */
import { aramaNormalize, aramaEslesir } from "@/utils/aramaNormalize";

describe("aramaNormalize", () => {
  it("KRİTİK: İ ile yazılmış kaydı küçük 'i' ile arayınca bulur", () => {
    expect(aramaEslesir("İpek", "ipek")).toBe(true);
    expect(aramaEslesir("İnci", "inci")).toBe(true);
  });

  it("KRİTİK: I ile yazılmış kaydı doğru Türkçe 'ı' ile arayınca bulur", () => {
    expect(aramaEslesir("IŞIK", "ışık")).toBe(true);
    expect(aramaEslesir("Işık", "ışık")).toBe(true);
    expect(aramaEslesir("Ilgaz", "ılgaz")).toBe(true);
  });

  it("KRİTİK: birleşik nokta (U+0307) kalıntısı bırakmaz", () => {
    // Asıl kusur buydu: "İ".toLowerCase() → 'i' + U+0307 → hiçbir sorguya eşleşmiyordu.
    expect(aramaNormalize("İpek")).not.toContain("̇");
    expect(aramaNormalize("İpek")).toBe("ipek");
  });

  it("iki yön de çalışır: büyük harfle aranan küçük harfli kaydı bulur", () => {
    expect(aramaEslesir("ipek", "İPEK")).toBe(true);
    expect(aramaEslesir("ışık", "IŞIK")).toBe(true);
  });

  it("karşı-kanıt: ALAKASIZ sorgu eşleşmez (normalize fazla agresif değil)", () => {
    expect(aramaEslesir("İpek", "pamuk")).toBe(false);
    expect(aramaEslesir("Işık", "isik-degil")).toBe(false);
  });

  it("karşı-kanıt: ş/ç/ğ/ü/ö ayrımı KORUNUR (aksan silme YAPILMAZ)", () => {
    // Aksanları düzleştirmek "Şirin" ile "Sirin"i birleştirir; bu bir hasta-kimliği ekranıdır,
    // yanlış eşleşme yanlış kayda bakmak demektir. Kapsam yalnız İ/I kuralı.
    expect(aramaEslesir("Şirin", "sirin")).toBe(false);
    expect(aramaEslesir("Gökçe", "gokce")).toBe(false);
  });

  it("karşı-kanıt: boş sorgu / boş metin çökmez", () => {
    expect(aramaEslesir("", "")).toBe(true);
    expect(aramaEslesir("Pamuk", "")).toBe(true);
    expect(aramaEslesir("", "pamuk")).toBe(false);
  });

  it("karşı-kanıt: null/undefined güvenli", () => {
    expect(aramaEslesir(undefined, "x")).toBe(false);
    expect(aramaEslesir("Pamuk", undefined)).toBe(true);
    expect(aramaNormalize(null)).toBe("");
  });

  it("sorgu baştaki/sondaki boşlukla eşleşmeyi bozmaz", () => {
    expect(aramaEslesir("İpek", "  ipek  ")).toBe(true);
  });

  it("düz ASCII davranışı DEĞİŞMEZ (geriye uyum)", () => {
    expect(aramaEslesir("Pamuk", "pam")).toBe(true);
    expect(aramaEslesir("Pamuk", "MUK")).toBe(true);
  });
});

describe("üç arama yüzeyi de tek kaynağı kullanır", () => {
  // Yapısal çıpa: bu bulgunun kök nedeni AYNI kuralın üç yerde kopyalanmasıydı. Kopya, kuralın
  // bir yerde düzeltilip diğerinde kalması demektir ("kısmi düzeltme, düzeltilmemiş demektir").
  const fs = require("fs");
  const path = require("path");
  const kok = path.resolve(__dirname, "..", "..");

  it.each([
    ["screens/PatientScreen.tsx"],
    ["screens/TreatmentHistoryScreen.tsx"],
    ["components/domain/PatientGate.tsx"],
  ])("%s ham toLowerCase ile süzmez", (dosya) => {
    const src = fs.readFileSync(path.join(kok, dosya), "utf8");
    const kodSatirlari = src
      .split("\n")
      .filter((s: string) => !s.trim().startsWith("//") && !s.trim().startsWith("*"));
    const suzmeSatirlari = kodSatirlari.filter(
      (s: string) => s.includes(".includes(") && s.includes("toLowerCase()"),
    );
    expect(suzmeSatirlari).toEqual([]);
    // ⚠️ Yalnız "dosyada `aramaEslesir` geçiyor mu" YETMEZ: çağrı varken import EKSİK olabilir
    // (ilk denememde tam bu oldu ve yalnız `tsc` yakaladı). İçe alımı da AÇIKÇA denetle.
    expect(src).toMatch(/import\s*\{[^}]*aramaEslesir[^}]*\}\s*from\s*["']@\/utils\/aramaNormalize["']/);
  });
});
