// Author: mertaygn
/**
 * TAKİP SERİSİ — aynı hayvanın analizleri zaman içinde (sahip isteği 2026-09-12, öneri #4).
 * =======================================================================================
 * "evcil hayvan modunda ... neler ekleyebileceğimizi düşün."
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * ⚠️ BU ÖNERİ EN SONA KONULMUŞTU VE SEBEBİ BURADA KODLANIYOR
 * ═══════════════════════════════════════════════════════════════════════════════
 * `result_detail` HETEROJENDİR: her modül kendi alanlarını yazar. Hepsini tek bir çizgiye
 * dizmek ANLAMSIZ olurdu — "yara kapanma %42" ile "böbrek sınıfı 3"ü aynı eksende
 * göstermek, bilgi değil gürültü üretir.
 *
 * KURAL: seri YALNIZ **aynı modülün** ve **aynı ölçütün** kayıtlarından kurulur. Karışık
 * modüllü bir geçmişte, en çok kaydı olan modül seçilir ve diğerleri DIŞARIDA bırakılır
 * (sessizce değil — çağıran `disaridaKalan` sayısını gösterir).
 *
 * ⚠️ TEK NOKTA ÇİZİLMEZ: iki ölçümden azı "eğilim" göstermez; tek noktalı bir grafik
 * kullanıcıya var olmayan bir takip vaat eder.
 */
import type { AnalizKaydi } from "@/utils/sonAnaliz";

/** Zaman serisine alınabilecek sayısal ölçütler — modül bazında, TÜRKÇE etiketleriyle. */
export const IZLENEN_OLCUTLER: Record<string, { alan: string; etiket: string; birim: string }> = {
  cell_scratch: { alan: "closure_pct", etiket: "Kapanma", birim: "%" },
  em_petri: { alan: "n_wells", etiket: "Kuyu", birim: "" },
  em_fantom: { alan: "n_tumors", etiket: "Tümör", birim: "" },
};

/** Hiçbir modüle özgü ölçüt yoksa kullanılan evrensel ölçüt. */
export const VARSAYILAN_OLCUT = { alan: "confidence", etiket: "Güven", birim: "%" };

export interface TakipNoktasi {
  /** Epoch ms — sıralama ve eksen için. */
  t: number;
  deger: number;
  etiket: string;
}

export interface TakipSerisi {
  moduleId: string;
  baslik: string;
  birim: string;
  noktalar: TakipNoktasi[];
  /** Başka modüle ait olduğu için seriye ALINMAYAN kayıt sayısı (kullanıcıya söylenir). */
  disaridaKalan: number;
}

/**
 * ⚠️ `result_detail` ÜRETİMDE `unknown` TİPİNDE: her modül kendi şeklini yazar ve tip
 * sistemi onu daraltamaz. Burada `unknown` kabul edilip OKURKEN daraltılır — `Record`
 * diye tipleyip zorlamak, gerçekte sözlük OLMAYAN bir değerde çalışma anında çökerdi.
 */
interface DetayliKayit extends AnalizKaydi {
  result_detail?: unknown;
}

/** `result_detail`i güvenle sözlük olarak okur (değilse boş sözlük). */
function detaySozlugu(d: unknown): Record<string, unknown> {
  return d && typeof d === "object" && !Array.isArray(d) ? (d as Record<string, unknown>) : {};
}

/**
 * Bir hastanın kayıtlarından TEK ölçütlü takip serisi kurar.
 *
 * Dönen `null`: çizilecek anlamlı bir seri yok (kayıt yok · tek nokta · sayısal ölçüt yok).
 * ⚠️ `null` dönmek, boş bir grafik çizmekten İYİDİR: boş eksen "veri mi yok, bozuk mu?"
 * sorusunu doğurur.
 */
export function takipSerisiKur(kayitlar: readonly DetayliKayit[] | null | undefined): TakipSerisi | null {
  const liste = (kayitlar ?? []).filter((k) => k && Number.isFinite(Date.parse(k.created_at ?? "")));
  if (liste.length < 2) return null;

  // En çok kaydı olan modülü seç — seri onun üzerinden kurulur.
  const sayac = new Map<string, number>();
  for (const k of liste) {
    const m = String(k.module_id || k.module_label || "");
    if (m) sayac.set(m, (sayac.get(m) ?? 0) + 1);
  }
  let modul = "";
  let enCok = 0;
  for (const [m, n] of sayac) {
    if (n > enCok) {
      modul = m;
      enCok = n;
    }
  }
  if (!modul) return null;

  const olcut = IZLENEN_OLCUTLER[modul] ?? VARSAYILAN_OLCUT;
  const ayni = liste.filter((k) => String(k.module_id || k.module_label || "") === modul);

  const noktalar: TakipNoktasi[] = [];
  for (const k of ayni) {
    const ham = olcut.alan === "confidence" ? k.confidence : detaySozlugu(k.result_detail)[olcut.alan];
    const sayi = typeof ham === "number" ? ham : Number(ham);
    if (!Number.isFinite(sayi)) continue;
    // Güven 0-1 aralığında saklanır; yüzdeye çevrilir (etiket "%" diyor).
    const deger = olcut.alan === "confidence" ? Math.round(sayi * 100) : sayi;
    const t = Date.parse(k.created_at ?? "");
    noktalar.push({ t, deger, etiket: new Date(t).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" }) });
  }
  // ⚠️ Eskiden yeniye: grafik soldan sağa zamanı izlemeli.
  noktalar.sort((a, b) => a.t - b.t);

  // ⚠️ TEK NOKTA ÇİZİLMEZ (bkz. dosya başlığı).
  if (noktalar.length < 2) return null;

  return {
    moduleId: modul,
    baslik: olcut.etiket,
    birim: olcut.birim,
    noktalar,
    disaridaKalan: liste.length - ayni.length,
  };
}
