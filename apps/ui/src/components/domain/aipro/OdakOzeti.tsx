// Author: mertaygn, cglrgrkn
/**
 * ODAK ÖZETİ (istem 45 · Y273 / Y274): AI Pro onay penceresinde faz / duty'yi üreten ODAK planının fizik denetimi.
 * Eski "hedefte · çevrede · oran" satırının (hoca modelinin birimsiz E'si — yanlış) YERİNE:
 *  - seçilen DOZ (hedefte tepe |B|, mT) ± konum payı (hedef 1 cm kayınca doz değişimi), beklenen (zaman domeni, Y280 hizalı), TAVAN
 *    (o konumda duty ≤ %50 ile verilebilen en büyük doz), çevre ortalaması + oran (odak kipleri) ya da düzgünlük (TÜM PETRİ / tüm vücut);
 *  - PETRİDE ZORUNLU 24 kuyu KÜÇÜK HARİTASI: plakanın KAMERADAKİ yönüyle (kuyular karedeki piksel konumlarına yerleşir), seçili kuyu
 *    işaretli, her kuyuda mT + renk ölçeği + "komşu kuyular da alan alır" (renk + sayı birlikte — renk körlüğü);
 *  - DOZ SEÇİCİ (üst sınır = tavan) + petri kipi (TÜM PETRİ / KUYUCUK) → "Yeniden hesapla" yeni öneri ister (mühür yeni öneride).
 *  - ODD B-2 (ODK-B keşfi 18-11): doz / kip / kuyu değişip yeniden hesaplanmadıysa (KİRLİ) harita "önceki plan" olarak soluk, uyarı
 *    görünür ve üst bileşen (`onKirli`) "Onayla ve Başlat"ı PASİF yapar — onaylanan = ekranda görünen. Tavan YALNIZ hesaplandığı kipte
 *    geçerlidir: kip değişince "en çok" sayısı gösterilmez ("Yeniden hesapla'dan sonra"), doğrulama yalnız > 0 (sunucu tavanı denetler).
 *    Yeni öneri gelince (yeni `odak`) yerel seçim onunla eşitlenir.
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import i18n from "i18next";

import { colors, radius, rf, rs, spacing, touch, typography } from "@/theme/tokens";

/** ODK11: `bos` = kamerada sıvı görülmeyen kuyu (yeri plakanın görülen kuyularından hesaplandı) — soluk çizilir, hedef olamaz. */
export type OdakKuyu = { etiket: string; px?: number[] | null; mT: number | null; secili?: boolean; bos?: boolean };
export type OdakOzet = {
  kip: string;
  doz_mT: number;
  beklenen_mT?: number;
  tavan_mT?: number;
  cevre_mT?: number | null;
  oran?: number;
  pay_yuzde?: number;
  sapma_yuzde?: number;
  kuyular?: OdakKuyu[];
  /** ODK8: sürüş frekansı (Hz) — mühürde; yoksa eski mühür (100 Hz). */
  frek_hz?: number;
};

export const PETRI_KIPLERI = ["KUYUCUK", "TUM_PETRI"] as const;

/** Dile uyan ondalık (TR "1,25", EN "1.25"). */
export function sayi(n: number | null | undefined, basamak = 2): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return n.toFixed(basamak).replace(".", i18n.language === "en" ? "." : ",");
}

/** Kullanıcının yazdığı doz ("1,2" / "1.2") → sayı; geçersiz → NaN. */
export function dozCoz(metin: string): number {
  const t = String(metin ?? "").trim().replace(",", ".");
  return /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
}

const DUSUK = [37, 99, 235]; // mavi (düşük)
const YUKSEK = [220, 38, 38]; // kırmızı (yüksek)

/** mT → renk "#rrggbb" (düşük mavi → yüksek kırmızı, doğrusal). */
export function kuyuRengi(v: number | null, min: number, maks: number): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return colors.bgAlt;
  const t = maks > min ? Math.min(1, Math.max(0, (v - min) / (maks - min))) : 1;
  return "#" + DUSUK.map((d, i) => Math.round(d + (YUKSEK[i] - d) * t).toString(16).padStart(2, "0")).join("");
}

const SATIR = "ABCD";
const HUCRE = 40;
const KUTU_G = 6 * (HUCRE + 4);
const KUTU_Y = 4 * (HUCRE + 4);

/** Kuyunun haritadaki yeri (0..1): kameradaki piksel konumu (yön korunur); px yoksa etiketten ızgara (A1 sol üst). */
export function kuyuKonumlari(kuyular: OdakKuyu[]): { x: number; y: number }[] {
  const pxVar = kuyular.length > 0 && kuyular.every((k) => Array.isArray(k.px) && k.px.length >= 2 && k.px.every(Number.isFinite));
  if (pxVar) {
    const us = kuyular.map((k) => Number(k.px![0]));
    const vs = kuyular.map((k) => Number(k.px![1]));
    const [u0, u1, v0, v1] = [Math.min(...us), Math.max(...us), Math.min(...vs), Math.max(...vs)];
    return kuyular.map((_, i) => ({
      x: u1 > u0 ? (us[i] - u0) / (u1 - u0) : 0.5,
      y: v1 > v0 ? (vs[i] - v0) / (v1 - v0) : 0.5,
    }));
  }
  return kuyular.map((k) => {
    const r = SATIR.indexOf(String(k.etiket).charAt(0).toUpperCase());
    const c = Number(String(k.etiket).slice(1)) - 1;
    return r >= 0 && c >= 0 && c <= 5 ? { x: c / 5, y: r / 3 } : { x: 0.5, y: 0.5 };
  });
}

export function KuyuHaritasi({
  kuyular,
  secilen,
  onSec,
  eski = false,
}: {
  kuyular: OdakKuyu[];
  /** AP-B3: kullanıcının haritada seçtiği kuyu (yoksa mühürdeki `secili`). */
  secilen?: string;
  /** AP-B3: verilirse DOLU kuyular dokunulabilir (boş kuyu hedef OLAMAZ — ODK11); seçim "Yeniden hesapla" ile yeni öneri ister. */
  onSec?: (etiket: string) => void;
  /** ODD B-2: seçim değişti, harita hâlâ ÖNCEKİ planı gösteriyor → soluk + "önceki plan" etiketi. */
  eski?: boolean;
}) {
  const { t } = useTranslation();
  const degerler = kuyular.map((k) => k.mT).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const min = degerler.length ? Math.min(...degerler) : 0;
  const maks = degerler.length ? Math.max(...degerler) : 0;
  const yer = kuyuKonumlari(kuyular);
  const bosSayi = kuyular.filter((k) => k.bos).length;
  return (
    <View testID="odak-kuyu-haritasi" accessibilityLabel={t("ai.pro.onay.odak.haritaBaslik")}>
      <Text style={s.haritaBaslik}>{t("ai.pro.onay.odak.haritaBaslik")}</Text>
      {eski ? <Text testID="odak-harita-eski" style={s.uyari}>{t("ai.pro.onay.odak.eskiPlan")}</Text> : null}
      <View style={[s.kutu, { width: rs(KUTU_G), height: rs(KUTU_Y) }, eski && s.eski]}>
        {kuyular.map((k, i) => {
          const isaretli = secilen ? k.etiket === secilen : !!k.secili;
          const etiket = isaretli
            ? t("ai.pro.onay.odak.kuyuEtiketSecili", { etiket: k.etiket, deger: sayi(k.mT), secili: t("ai.pro.onay.odak.secili") })
            : k.bos
              ? t("ai.pro.onay.odak.kuyuEtiketBos", { etiket: k.etiket, deger: sayi(k.mT) })
              : t("ai.pro.onay.odak.kuyuEtiket", { etiket: k.etiket, deger: sayi(k.mT) });
          const stil = [
            s.hucre,
            {
              left: yer[i].x * rs(KUTU_G - HUCRE - 4),
              top: yer[i].y * rs(KUTU_Y - HUCRE - 4),
              backgroundColor: kuyuRengi(k.mT, min, maks),
            },
            isaretli && s.hucreSecili,
            k.bos && s.hucreBos,
          ];
          const icerik = (
            <>
              <Text style={s.hucreEtiket}>{k.etiket}</Text>
              <Text style={s.hucreDeger}>{sayi(k.mT)}</Text>
            </>
          );
          // AP-B3: dolu kuyu dokunulabilir; boş kuyu (ODK11) ve harita salt gösterimken (onSec yok) eskisi gibi düz kutu.
          return onSec && !k.bos ? (
            <TouchableOpacity
              key={k.etiket}
              testID={k.secili ? "odak-kuyu-secili" : `odak-kuyu-${k.etiket}`}
              accessibilityLabel={etiket}
              accessibilityRole="button"
              accessibilityHint={t("ai.pro.onay.odak.kuyuSecIpucu")}
              accessibilityState={{ selected: isaretli }}
              onPress={() => onSec(k.etiket)}
              style={[...stil, { minHeight: touch.min, minWidth: touch.min }]}
            >
              {icerik}
            </TouchableOpacity>
          ) : (
            <View key={k.etiket} testID={k.secili ? "odak-kuyu-secili" : `odak-kuyu-${k.etiket}`} accessibilityLabel={etiket} style={stil}>
              {icerik}
            </View>
          );
        })}
      </View>
      <Text style={s.olcek}>{t("ai.pro.onay.odak.olcek", { min: sayi(min), maks: sayi(maks) })}</Text>
      <Text style={s.uyari}>{t("ai.pro.onay.odak.komsuUyari")}</Text>
      {bosSayi > 0 ? (
        <Text testID="odak-bos-kuyu" style={s.olcek}>{t("ai.pro.onay.odak.bosKuyu", { sayi: bosSayi })}</Text>
      ) : null}
    </View>
  );
}

export function OdakOzeti({
  odak, busy, onYenidenHesapla, onKirli, konumEski, onKonumTazele,
}: {
  odak: OdakOzet;
  busy?: boolean;
  /** Doz / petri kipi / (AP-B3) haritadan seçilen kuyu değişince yeni öneri iste (yeni mühür). Verilmezse seçici gösterilmez. */
  onYenidenHesapla?: (doz: number, kip: string, kuyu?: string) => void;
  /** ODD B-2: ekrandaki seçim ile önerinin (mühürün) planı ayrıştı mı — üst bileşen onayı buna göre PASİF yapar. */
  onKirli?: (kirli: boolean) => void;
  /** ODD B-3: konum ölçümü 2 dk'ya yaklaştı / geçti — "Konumu tazele ve yeniden hesapla" görünür (yalnız işleyici verildiyse). */
  konumEski?: boolean;
  /** ODD B-3: önizlemeyi kısa açıp taze konumla AYNI doz / kip / kuyuyla yeniden öneri iste (web — sunucu kamerası). */
  onKonumTazele?: (doz: number, kip: string, kuyu?: string) => void;
}) {
  const { t } = useTranslation();
  const [dozMetni, setDozMetni] = useState(sayi(odak.doz_mT));
  const [kip, setKip] = useState(odak.kip);
  /** AP-B3: mühürdeki kuyu (öneri) ve kullanıcının haritada seçtiği kuyu. */
  const muhurKuyusu = (odak.kuyular || []).find((k) => k.secili)?.etiket || "";
  const [secilenKuyu, setSecilenKuyu] = useState(muhurKuyusu);
  // ODD B-2: yeni öneri (yeni plan) gelince yerel seçim onunla eşitlenir — eski seçim yeni planı "kirli" göstermesin.
  useEffect(() => {
    setDozMetni(sayi(odak.doz_mT));
    setKip(odak.kip);
    setSecilenKuyu((odak.kuyular || []).find((k) => k.secili)?.etiket || "");
  }, [odak]);
  const kuyuDegisti = !!secilenKuyu && secilenKuyu !== muhurKuyusu;
  // ODD B-2: tavan YALNIZ hesaplandığı kipte geçerli (TÜM PETRİ ↔ KUYUCUK tavanı farklı) — kip değişince sayı söylenmez.
  const tavanGecerli = kip === odak.kip && typeof odak.tavan_mT === "number";
  const tavan = tavanGecerli ? (odak.tavan_mT as number) : NaN;
  const doz = dozCoz(dozMetni);
  const dozGecerli = Number.isFinite(doz) && doz > 0 && (!Number.isFinite(tavan) || doz <= tavan);
  // ODD B-2: ekrandaki seçim önerinin planından farklı (ya da doz okunamıyor) → KİRLİ: harita / tablo önceki plan, onay pasif.
  const kirli = !(Number.isFinite(doz) && Math.abs(doz - odak.doz_mT) < 0.005) || kip !== odak.kip || kuyuDegisti;
  useEffect(() => {
    onKirli?.(kirli);
  }, [kirli, onKirli]);
  const petri = (PETRI_KIPLERI as readonly string[]).includes(odak.kip);
  const duzgunluk = odak.kip === "TUM_PETRI" || odak.kip === "KEDI_TV";

  return (
    <View testID="odak-ozeti" style={s.wrap}>
      <Text style={s.satirKalin}>
        {t("ai.pro.onay.odak.doz", { doz: sayi(odak.doz_mT), pay: sayi(odak.pay_yuzde, 0) })}
      </Text>
      <Text testID="odak-frekans" style={s.satir}>
        {t("ai.pro.onay.odak.frekans", { f: odak.frek_hz ?? 100 })}
      </Text>
      <Text style={s.satir}>
        {t("ai.pro.onay.odak.beklenen", { beklenen: sayi(odak.beklenen_mT), tavan: sayi(odak.tavan_mT) })}
      </Text>
      {duzgunluk ? (
        <Text style={s.satir}>{t("ai.pro.onay.odak.duzgunluk", { oran: sayi(odak.oran) })}</Text>
      ) : (
        <Text style={s.satir}>{t("ai.pro.onay.odak.cevre", { cevre: sayi(odak.cevre_mT), oran: sayi(odak.oran, 1) })}</Text>
      )}
      <Text style={s.kaynak}>{t("ai.pro.onay.odak.kaynak")}</Text>

      {Array.isArray(odak.kuyular) && odak.kuyular.length ? (
        <KuyuHaritasi
          kuyular={odak.kuyular}
          eski={kirli}
          secilen={secilenKuyu || undefined}
          onSec={
            onYenidenHesapla
              ? (e) => {
                  setSecilenKuyu(e);
                  if (kip !== "KUYUCUK") setKip("KUYUCUK"); // tek kuyu hedefi KUYUCUK kipindedir
                }
              : undefined
          }
        />
      ) : null}
      {onYenidenHesapla && Array.isArray(odak.kuyular) && odak.kuyular.length ? (
        <Text testID="odak-kuyu-sec-ipucu" style={kuyuDegisti ? s.uyari : s.olcek}>
          {kuyuDegisti ? t("ai.pro.onay.odak.secilenKuyu", { etiket: secilenKuyu }) : t("ai.pro.onay.odak.haritaSecIpucu")}
        </Text>
      ) : null}

      {onYenidenHesapla ? (
        <View style={s.secici}>
          {petri ? (
            <View style={s.kipSatiri} accessibilityRole="radiogroup" accessibilityLabel={t("ai.pro.onay.odak.kipEtiket")}>
              {PETRI_KIPLERI.map((k) => (
                <TouchableOpacity
                  key={k}
                  testID={`odak-kip-${k}`}
                  style={[s.kipDugme, kip === k && s.kipDugmeSecili, { minHeight: touch.min }]}
                  onPress={() => setKip(k)}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: kip === k }}
                >
                  <Text style={[s.kipYazi, kip === k && s.kipYaziSecili]}>{t(`ai.pro.onay.odak.kip.${k}`)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
          <Text testID="odak-doz-etiket" style={s.satir}>
            {tavanGecerli ? t("ai.pro.onay.odak.dozSec", { tavan: sayi(tavan) }) : t("ai.pro.onay.odak.dozSecKipDegisti")}
          </Text>
          <View style={s.dozSatiri}>
            <TextInput
              testID="odak-doz-girdi"
              style={[s.girdi, { minHeight: touch.min }]}
              value={dozMetni}
              onChangeText={setDozMetni}
              keyboardType="decimal-pad"
              accessibilityLabel={tavanGecerli ? t("ai.pro.onay.odak.dozSec", { tavan: sayi(tavan) }) : t("ai.pro.onay.odak.dozSecKipDegisti")}
            />
            <TouchableOpacity
              testID="odak-yeniden-hesapla"
              style={[s.dugme, (!dozGecerli || busy) && s.dugmePasif, { minHeight: touch.min }]}
              disabled={!dozGecerli || !!busy}
              onPress={() => onYenidenHesapla(doz, kip, kuyuDegisti ? secilenKuyu : undefined)}
              accessibilityRole="button"
              accessibilityState={{ disabled: !dozGecerli || !!busy }}
            >
              <Text style={s.dugmeYazi}>{t("ai.pro.onay.odak.yenidenHesapla")}</Text>
            </TouchableOpacity>
          </View>
          {!dozGecerli ? (
            <Text testID="odak-doz-hata" style={s.uyari}>
              {tavanGecerli ? t("ai.pro.onay.odak.dozGecersiz", { tavan: sayi(tavan) }) : t("ai.pro.onay.odak.dozGecersizTavansiz")}
            </Text>
          ) : null}
          {kirli ? (
            <Text testID="odak-kirli" style={s.uyari} accessibilityLiveRegion="polite">{t("ai.pro.onay.odak.kirliUyari")}</Text>
          ) : null}
          {konumEski && onKonumTazele ? (
            <>
              <Text testID="odak-konum-eski" style={s.uyari}>{t("ai.pro.onay.odak.konumEskiUyari")}</Text>
              <TouchableOpacity
                testID="odak-konum-tazele"
                style={[s.dugme, s.dugmeGenis, (!dozGecerli || busy) && s.dugmePasif, { minHeight: touch.min }]}
                disabled={!dozGecerli || !!busy}
                onPress={() => onKonumTazele(doz, kip, kuyuDegisti ? secilenKuyu : undefined)}
                accessibilityRole="button"
                accessibilityState={{ disabled: !dozGecerli || !!busy }}
              >
                <Text style={s.dugmeYazi}>{t("ai.pro.onay.odak.konumTazele")}</Text>
              </TouchableOpacity>
            </>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { gap: spacing.xs, marginTop: spacing.xs },
  satir: { color: colors.text, fontSize: rf(12), fontWeight: "600" },
  satirKalin: { color: colors.text, fontSize: rf(13), fontWeight: "800" },
  kaynak: { color: colors.textMuted, fontSize: rf(11) },
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
  haritaBaslik: { color: colors.text, fontSize: rf(12), fontWeight: "700", marginTop: spacing.xs },
  kutu: { position: "relative", marginTop: spacing.xs, backgroundColor: colors.bgAlt, borderRadius: radius.md },
  hucre: {
    position: "absolute",
    width: rs(HUCRE),
    height: rs(HUCRE),
    borderRadius: rs(HUCRE / 2),
    alignItems: "center",
    justifyContent: "center",
  },
  hucreSecili: { borderWidth: 3, borderColor: colors.text },
  hucreBos: { opacity: 0.35, borderWidth: 1, borderStyle: "dashed", borderColor: colors.textMuted },
  eski: { opacity: 0.4 },
  // KP-5: punto kapısı (test_arayuz_yazi_olcegi_kapisi) — en küçük okunur punto typography.small (11); 40 px dairede iki satır sığar.
  hucreEtiket: { color: "#FFFFFF", fontSize: typography.small, fontWeight: "800" },
  hucreDeger: { color: "#FFFFFF", fontSize: typography.small, fontWeight: "700" },
  olcek: { color: colors.textMuted, fontSize: rf(11) },
  secici: { gap: spacing.xs, marginTop: spacing.sm },
  kipSatiri: { flexDirection: "row", gap: spacing.xs },
  kipDugme: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  kipDugmeSecili: { backgroundColor: colors.primary, borderColor: colors.primary },
  kipYazi: { color: colors.text, fontSize: rf(12), fontWeight: "700" },
  kipYaziSecili: { color: "#04121F" },
  dozSatiri: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  girdi: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.sm,
    color: colors.text,
    fontSize: rf(13),
  },
  dugme: { backgroundColor: colors.primary, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: "center" },
  dugmePasif: { opacity: 0.5 },
  dugmeGenis: { alignItems: "center", paddingVertical: spacing.xs },
  dugmeYazi: { color: "#04121F", fontSize: rf(12), fontWeight: "800" },
});
