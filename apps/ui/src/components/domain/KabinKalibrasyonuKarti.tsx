/**
 * KABİN KALİBRASYONU (KD · sahip kararları Y258–Y260; KD-2 çok konumlu, 2026-11-10) — sabit düzlem kalibrasyonu ekranı. Araştırma
 * profili, AI Pro panelinde petri / fantom modeliyle; masaüstü + telefon + web (kare ARKA UÇTAKİ kabin kamerasından gelir).
 *
 * Akış (KD-2 — gerçek tezgâh karelerinde tek konum başka yerde 2,5 cm'ye kaçtı): plakayı kabinin bir yanına koy → Kare al (kuyular
 * sunucuda OTOMATİK bulunur, köşeler görüntüde 1–4 numaralı çizilir; dokunma yok) → numaralı köşelerden en az ikisinin (tercihen
 * çapraz) sol / ön cama uzaklığı → Konumu ekle → plakayı öbür yana koy, tekrarla → lens konumu → Hesapla → Kaydet (lens uyarısı AÇIK
 * onay ister). "Doğrula": plaka başka yerde, ≥ 1 köşe → plaka MERKEZİ farkı. Numune tabanı (altlık) ve "kalibre etmeden devam"
 * (kamera ~≤ 2 cm oynadıysa) aynı kartta. Bütün kurallar / eşikler / nedenler arka uçtan (`/api/ai/pro/kalibrasyon/*`).
 */
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Crosshair } from "lucide-react-native";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { AI_TIMEOUT_MS, apiGet, apiPost, KAMERA_TIMEOUT_MS } from "@/services/apiClient";

type Kip = "kalibrasyon" | "dogrulama";
interface Kare {
  kareKimligi: string;
  genislik: number;
  yukseklik: number;
  image_base64: string;
  plaka: { bulundu: boolean; kuyuSayisi: number; kareSayisi: number; metin: string | null };
}
interface Olcu {
  sol: string;
  on: string;
}
interface Konum {
  kareKimligi: string;
  olcum: Olcu[];
}
interface Durum {
  var: boolean;
  gecerli: boolean;
  hataMetni?: string;
  tarih?: string;
  konumSayisi?: number;
  izdusumHatasiPx?: number;
  lensFarkiCm?: number | null;
  kameraAdi?: string | null;
  kameraVidPid?: string | null;
  olculenLensTabanCm?: number | null;
  gorusAlani?: { on: number | null; arka: number | null; sol: number | null; sag: number | null } | null;
  sahneDenetimi?: boolean;
  eski?: boolean;
  eskiTarih?: string | null;
  tabanYukseltmesiCm?: number;
  fantom?: { kalinlikCm: number | null; tumorDerinligiCm: number | null; boyCm: (number | null)[] | null };
}
interface Sonuc {
  gecerli: boolean;
  nedenler: { kod: string; metin: string }[];
  izdusumHatasiPx: number | null;
  olcumUyumuMm: number | null;
  yayilimCm: number | null;
  konumlar: { koseSapmasiMm: (number | null)[]; kuyuIzdusumPx: number; merkezCm: number[] }[];
  caprazDogrulamaCm: (number | null)[] | null;
  hesaplananLensCm: number[] | null;
  olculenLensCm: number[] | null;
  lensYatayFarkiCm: number | null;
  lensDikeyFarkiCm: number | null;
  lensUyarisi: boolean;
  gorusAlani: { onCm: number | null; arkaCm: number | null; solCm: number | null; sagCm: number | null } | null;
  sahne: { oznitelik: number; denetim: boolean } | null;
  esikler: { izdusumPx: number; lensCm: number; lensDikeyCm: number; olcumMm: number; yayilimCm: number; konumAsgari: number };
}
interface Dogrulama {
  farkCm: (number | null)[];
  merkezFarkCm: number;
  gecti: boolean;
  esikCm: number;
}

const sayi = (s: string) => Number(String(s).replace(",", "."));
const gecerliSayi = (s: string) => s.trim() !== "" && Number.isFinite(sayi(s));
const bosOlcu = (): Olcu[] => Array.from({ length: 4 }, () => ({ sol: "", on: "" }));
const olculen = (o: Olcu[]) => o.filter((x) => gecerliSayi(x.sol) && gecerliSayi(x.on)).length;
const cm = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));

export function KabinKalibrasyonuKarti({ model, kilitli = false }: { model: "petri" | "fantom"; kilitli?: boolean }) {
  const { t } = useTranslation();
  const [durum, setDurum] = useState<Durum | null>(null);
  const [kip, setKip] = useState<Kip | null>(null);
  const [kare, setKare] = useState<Kare | null>(null);
  const [aliniyor, setAliniyor] = useState(false);
  const [olcum, setOlcum] = useState<Olcu[]>(bosOlcu());
  const [konumlar, setKonumlar] = useState<Konum[]>([]);
  const [lens, setLens] = useState({ sol: "", on: "", taban: "" });
  const [plakaYuk, setPlakaYuk] = useState("2");
  const [sonuc, setSonuc] = useState<Sonuc | null>(null);
  const [lensOnay, setLensOnay] = useState(false);
  const [dogrulama, setDogrulama] = useState<Dogrulama | null>(null);
  const [mesaj, setMesaj] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [genislik, setGenislik] = useState(0);
  const [fantom, setFantom] = useState({ kalinlik: "", derinlik: "", boy: "", en: "" });
  const [tabanUzaklik, setTabanUzaklik] = useState("");

  const yukle = useCallback(async () => {
    const d = await apiGet<Durum | null>("/ai/pro/kalibrasyon", null, { silent: true });
    setDurum(d);
    if (d?.fantom) {
      setFantom((f) => ({
        kalinlik: f.kalinlik || (d.fantom?.kalinlikCm != null ? String(d.fantom.kalinlikCm) : ""),
        derinlik: f.derinlik || (d.fantom?.tumorDerinligiCm != null ? String(d.fantom.tumorDerinligiCm) : ""),
        boy: f.boy || (d.fantom?.boyCm?.[0] != null ? String(d.fantom.boyCm[0]) : ""),
        en: f.en || (d.fantom?.boyCm?.[1] != null ? String(d.fantom.boyCm[1]) : ""),
      }));
    }
    if (d?.olculenLensTabanCm != null) {
      const yuk = d.tabanYukseltmesiCm ?? 0;
      setTabanUzaklik((s) => s || String(Math.round((d.olculenLensTabanCm! - yuk) * 10) / 10));
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const hataYakala = (status: number, detail: string | undefined, govde: unknown) => {
    const d = (govde as { detail?: unknown } | null)?.detail;
    if (d && typeof d === "object") {
      const o = d as { mesaj?: string; sonuc?: Sonuc };
      if (o.sonuc) setSonuc(o.sonuc);
      setMesaj(o.mesaj ?? null);
    } else {
      setMesaj(detail ?? t("ai.kalibrasyon.hata"));
    }
  };

  const kareAl = async () => {
    if (kilitli || aliniyor) return;
    setMesaj(null);
    setDogrulama(null);
    setOlcum(bosOlcu());
    setAliniyor(true);
    try {
      const k = await apiPost<Kare | null>("/ai/pro/kalibrasyon/kare", {}, null, {
        timeoutMs: KAMERA_TIMEOUT_MS,
        zamanAsimiMesaji: t("ai.kalibrasyon.kareZamanAsimi"),
        silent: true,
        onHttpError: hataYakala,
      });
      setKare(k);
    } finally {
      setAliniyor(false);
    }
  };

  const baslat = (yeni: Kip) => {
    if (kilitli || aliniyor) return;
    setKip(yeni);
    setKare(null);
    setSonuc(null);
    setLensOnay(false);
    if (yeni === "kalibrasyon") setKonumlar([]);
    void kareAl();
  };

  const gosterim = kare
    ? { w: Math.min(genislik || 320, 960), h: (Math.min(genislik || 320, 960) * kare.yukseklik) / kare.genislik }
    : null;

  // Numaralar arka uçla AYNI (`sabit_duzlem.KOSE_ADLARI`; görüntüde çizilen 1–4): ön-sol, ön-sağ, arka-sağ, arka-sol.
  const koseAdlari = [
    t("ai.kalibrasyon.kose.onSol"),
    t("ai.kalibrasyon.kose.onSag"),
    t("ai.kalibrasyon.kose.arkaSag"),
    t("ai.kalibrasyon.kose.arkaSol"),
  ];
  const plakaVar = kare?.plaka?.bulundu === true;
  const eklenebilir = plakaVar && olculen(olcum) >= 2;
  const dogrulanabilir = plakaVar && olculen(olcum) >= 1;
  const lensVar = gecerliSayi(lens.sol) && gecerliSayi(lens.on) && gecerliSayi(lens.taban);
  const asgari = sonuc?.esikler.konumAsgari ?? 2;

  const olcuGovdesi = (o: Olcu[]) =>
    o.map((x) => (gecerliSayi(x.sol) && gecerliSayi(x.on) ? { solCm: sayi(x.sol), onCm: sayi(x.on) } : null));

  const konumEkle = () => {
    if (!kare || !eklenebilir) return;
    setKonumlar((p) => [...p, { kareKimligi: kare.kareKimligi, olcum }]);
    setKare(null);
    setOlcum(bosOlcu());
    setSonuc(null);
  };

  const govde = () => ({
    konumlar: konumlar.map((k) => ({ kareKimligi: k.kareKimligi, olcumler: olcuGovdesi(k.olcum) })),
    lens: lensVar ? { solCm: sayi(lens.sol), onCm: sayi(lens.on), tabanCm: sayi(lens.taban) } : null,
    plakaYuksekligiCm: sayi(plakaYuk),
    lensUyarisiniOnayla: lensOnay,
  });

  const istek = async <T,>(yol: string, b: unknown, zaman = AI_TIMEOUT_MS) => {
    setMesgul(true);
    setMesaj(null);
    try {
      return await apiPost<T | null>(yol, b, null, { timeoutMs: zaman, silent: true, onHttpError: hataYakala });
    } finally {
      setMesgul(false);
    }
  };

  const hesapla = async () => {
    if (konumlar.length < 2 || mesgul) return;
    const r = await istek<Sonuc>("/ai/pro/kalibrasyon/hesapla", govde());
    if (r) setSonuc(r);
  };

  const kaydet = async () => {
    if (mesgul || !sonuc?.gecerli || (sonuc.lensUyarisi && !lensOnay)) return;
    const r = await istek<{ durum: Durum }>("/ai/pro/kalibrasyon/kaydet", govde());
    if (r?.durum) {
      setDurum(r.durum);
      setMesaj(t("ai.kalibrasyon.kaydedildi"));
      setKip(null);
      setKare(null);
      setKonumlar([]);
    }
  };

  const dogrula = async () => {
    if (!kare || !dogrulanabilir || mesgul) return;
    const r = await istek<Dogrulama>("/ai/pro/kalibrasyon/dogrula", { kareKimligi: kare.kareKimligi, olcumler: olcuGovdesi(olcum) });
    if (r) {
      setDogrulama(r);
      void yukle();
    }
  };

  const fantomKaydet = async () => {
    if (mesgul || !gecerliSayi(fantom.kalinlik)) return;
    const boyVar = gecerliSayi(fantom.boy) && gecerliSayi(fantom.en);
    const r = await istek<{ durum: Durum }>("/ai/pro/kalibrasyon/fantom", {
      kalinlikCm: sayi(fantom.kalinlik),
      tumorDerinligiCm: gecerliSayi(fantom.derinlik) ? sayi(fantom.derinlik) : 0,
      boyCm: boyVar ? sayi(fantom.boy) : null,
      enCm: boyVar ? sayi(fantom.en) : null,
    });
    if (r?.durum) {
      setDurum(r.durum);
      setMesaj(t("ai.kalibrasyon.fantom.kaydedildi"));
    }
  };

  const tabanUygula = async () => {
    if (mesgul || !gecerliSayi(tabanUzaklik)) return;
    const r = await istek<{ durum: Durum }>("/ai/pro/kalibrasyon/taban", { lensUzaklikCm: sayi(tabanUzaklik) });
    if (r?.durum) {
      setDurum(r.durum);
      setMesaj(t("ai.kalibrasyon.taban.kaydedildi", { cm: cm(r.durum.tabanYukseltmesiCm ?? 0) }));
    }
  };

  const devamEt = async () => {
    if (mesgul || kilitli) return;
    const r = await istek<{ durum: Durum; kaymaPx: number }>("/ai/pro/kalibrasyon/sahne-yenile", {}, KAMERA_TIMEOUT_MS);
    if (r?.durum) {
      setDurum(r.durum);
      setMesaj(t("ai.kalibrasyon.devam.tamam", { px: r.kaymaPx?.toFixed?.(0) ?? "?" }));
    }
  };

  const ga = durum?.gorusAlani;

  return (
    <View style={styles.kutu} testID="kabin-kalibrasyonu" onLayout={(e) => setGenislik(Math.round(e.nativeEvent.layout.width) - 2 * spacing.md)}>
      <View style={styles.satir}>
        <Crosshair color={colors.primary} size={20} />
        <Text style={styles.baslik}>{t("ai.kalibrasyon.baslik")}</Text>
      </View>
      <Text style={styles.aciklama}>{t("ai.kalibrasyon.aciklama")}</Text>
      {durum ? (
        durum.gecerli ? (
          <Text style={styles.durum} testID="kabin-kalibrasyonu-durum">
            {t("ai.kalibrasyon.durumVar", {
              tarih: String(durum.tarih ?? "").slice(0, 16).replace("T", " "),
              n: durum.konumSayisi ?? 0,
              px: (durum.izdusumHatasiPx ?? 0).toFixed(2),
              cm: cm(durum.lensFarkiCm),
            })}
          </Text>
        ) : (
          <Text style={[styles.durum, styles.uyari]} testID="kabin-kalibrasyonu-durum">
            {durum.hataMetni ?? t("ai.kalibrasyon.durumYok")}
          </Text>
        )
      ) : null}
      {durum?.gecerli && durum.kameraAdi ? (
        <Text style={styles.not} testID="kabin-kalibrasyonu-kamera">
          {t("ai.kalibrasyon.kamera", { ad: durum.kameraAdi, vidpid: durum.kameraVidPid ?? "?" })}
        </Text>
      ) : null}
      {durum?.gecerli && ga?.on ? (
        <Text style={styles.not} testID="kabin-kalibrasyonu-gorus">
          {t("ai.kalibrasyon.gorusAlani", { on: cm(ga.on) })}
        </Text>
      ) : null}
      {durum?.gecerli && durum.eski ? (
        <Text style={[styles.not, styles.dikkat]} testID="kabin-kalibrasyonu-eski">
          {t("ai.kalibrasyon.eski", { tarih: String(durum.eskiTarih ?? "").slice(0, 16).replace("T", " ") })}
        </Text>
      ) : null}
      {durum?.gecerli && durum.sahneDenetimi === false ? (
        <Text style={[styles.not, styles.uyari]} testID="kabin-kalibrasyonu-sahne-yok">
          {t("ai.kalibrasyon.sahneYok")}
        </Text>
      ) : null}

      <View style={styles.satir}>
        <TouchableOpacity
          style={[styles.dugme, (kilitli || aliniyor) && styles.kilitli]}
          onPress={() => baslat("kalibrasyon")}
          disabled={kilitli || aliniyor}
          accessibilityRole="button"
          testID="kabin-kalibrasyonu-baslat"
        >
          <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.kalibreEt")}</Text>
        </TouchableOpacity>
        {durum?.gecerli ? (
          <TouchableOpacity
            style={[styles.dugme, styles.ikincil, (kilitli || aliniyor) && styles.kilitli]}
            onPress={() => baslat("dogrulama")}
            disabled={kilitli || aliniyor}
            accessibilityRole="button"
            testID="kabin-kalibrasyonu-dogrula-baslat"
          >
            <Text style={[styles.dugmeMetni, styles.ikincilMetin]}>{t("ai.kalibrasyon.dogrula")}</Text>
          </TouchableOpacity>
        ) : null}
      </View>
      {kilitli ? <Text style={styles.not}>{t("ai.kalibrasyon.kilitli")}</Text> : null}

      {kip === "kalibrasyon" ? (
        <View style={styles.adimlar} testID="kabin-kalibrasyonu-konumlar">
          <Text style={styles.altBaslik}>{t("ai.kalibrasyon.konum.baslik", { n: konumlar.length, asgari })}</Text>
          <Text style={styles.not}>{t("ai.kalibrasyon.konum.ipucu")}</Text>
          {konumlar.map((k, i) => (
            <View key={k.kareKimligi} style={styles.satir} testID={`kabin-kalibrasyonu-konum-${i}`}>
              <Text style={styles.durum}>{t("ai.kalibrasyon.konum.satir", { n: i + 1, kose: olculen(k.olcum) })}</Text>
              <TouchableOpacity
                onPress={() => {
                  setKonumlar((p) => p.filter((_, j) => j !== i));
                  setSonuc(null);
                }}
                accessibilityRole="button"
                testID={`kabin-kalibrasyonu-konum-sil-${i}`}
              >
                <Text style={styles.baglanti}>{t("ai.kalibrasyon.konum.sil")}</Text>
              </TouchableOpacity>
            </View>
          ))}
          {!kare ? (
            <TouchableOpacity
              style={[styles.dugme, styles.ikincil, (kilitli || aliniyor) && styles.kilitli]}
              onPress={() => void kareAl()}
              disabled={kilitli || aliniyor}
              accessibilityRole="button"
              testID="kabin-kalibrasyonu-kare-al"
            >
              <Text style={[styles.dugmeMetni, styles.ikincilMetin]}>{t("ai.kalibrasyon.konum.kareAl", { n: konumlar.length + 1 })}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      {aliniyor ? (
        <View style={styles.satir} testID="kabin-kalibrasyonu-kare-aliniyor">
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.not}>{t("ai.kalibrasyon.kareAliniyor")}</Text>
        </View>
      ) : null}

      {kip && kare && gosterim ? (
        <View style={styles.adimlar}>
          <Image
            source={{ uri: `data:image/jpeg;base64,${kare.image_base64}` }}
            style={{ width: gosterim.w, height: gosterim.h }}
            accessibilityLabel={t("ai.kalibrasyon.kareEtiketi")}
            testID="kabin-kalibrasyonu-kare"
          />
          {plakaVar ? (
            <Text style={styles.not}>{kip === "kalibrasyon" ? t("ai.kalibrasyon.olcuAciklama") : t("ai.kalibrasyon.dogrulaAciklama")}</Text>
          ) : (
            <Text style={[styles.not, styles.uyari]} testID="kabin-kalibrasyonu-plaka-yok">
              {kare.plaka?.metin ?? t("ai.kalibrasyon.hata")}
            </Text>
          )}
          {plakaVar
            ? olcum.map((o, i) => (
                <View key={i} style={styles.koseSatiri} testID={`kabin-kalibrasyonu-kose-${i}`}>
                  <Text style={styles.koseAdi}>
                    {i + 1} · {koseAdlari[i]}
                  </Text>
                  <TextInput
                    style={styles.giris}
                    keyboardType="decimal-pad"
                    value={o.sol}
                    onChangeText={(s) => setOlcum((p) => p.map((x, j) => (j === i ? { ...x, sol: s } : x)))}
                    placeholder={t("ai.kalibrasyon.solCm")}
                    accessibilityLabel={`${i + 1} ${koseAdlari[i]} ${t("ai.kalibrasyon.solCm")}`}
                    testID={`kabin-kalibrasyonu-sol-${i}`}
                  />
                  <TextInput
                    style={styles.giris}
                    keyboardType="decimal-pad"
                    value={o.on}
                    onChangeText={(s) => setOlcum((p) => p.map((x, j) => (j === i ? { ...x, on: s } : x)))}
                    placeholder={t("ai.kalibrasyon.onCm")}
                    accessibilityLabel={`${i + 1} ${koseAdlari[i]} ${t("ai.kalibrasyon.onCm")}`}
                    testID={`kabin-kalibrasyonu-on-${i}`}
                  />
                </View>
              ))
            : null}
          <View style={styles.satir}>
            {kip === "kalibrasyon" ? (
              <TouchableOpacity
                style={[styles.dugme, !eklenebilir && styles.kilitli]}
                onPress={konumEkle}
                disabled={!eklenebilir}
                accessibilityRole="button"
                testID="kabin-kalibrasyonu-konum-ekle"
              >
                <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.konum.ekle")}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={[styles.dugme, (!dogrulanabilir || mesgul) && styles.kilitli]}
                onPress={() => void dogrula()}
                disabled={!dogrulanabilir || mesgul}
                accessibilityRole="button"
                testID="kabin-kalibrasyonu-dogrula"
              >
                {mesgul ? <ActivityIndicator color="#fff" /> : <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.dogrulaHesapla")}</Text>}
              </TouchableOpacity>
            )}
            <TouchableOpacity
              style={[styles.dugme, styles.ikincil, aliniyor && styles.kilitli]}
              onPress={() => void kareAl()}
              disabled={aliniyor}
              accessibilityRole="button"
              testID="kabin-kalibrasyonu-yeniden-kare"
            >
              <Text style={[styles.dugmeMetni, styles.ikincilMetin]}>{t("ai.kalibrasyon.yenidenKare")}</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}

      {kip === "kalibrasyon" && konumlar.length > 0 ? (
        <View style={styles.adimlar}>
          <Text style={styles.altBaslik}>{t("ai.kalibrasyon.lensBaslik")}</Text>
          <View style={styles.satir}>
            {(
              [
                ["sol", t("ai.kalibrasyon.lens.sol")],
                ["on", t("ai.kalibrasyon.lens.on")],
                ["taban", t("ai.kalibrasyon.lens.taban")],
              ] as const
            ).map(([a, etiket]) => (
              <TextInput
                key={a}
                style={styles.giris}
                keyboardType="decimal-pad"
                value={lens[a]}
                onChangeText={(s) => {
                  setLens((p) => ({ ...p, [a]: s }));
                  setSonuc(null);
                }}
                placeholder={etiket}
                accessibilityLabel={etiket}
                testID={`kabin-kalibrasyonu-lens-${a}`}
              />
            ))}
          </View>
          <View style={styles.satir}>
            <Text style={styles.not}>{t("ai.kalibrasyon.plakaYuksekligi")}</Text>
            <TextInput
              style={styles.giris}
              keyboardType="decimal-pad"
              value={plakaYuk}
              onChangeText={setPlakaYuk}
              accessibilityLabel={t("ai.kalibrasyon.plakaYuksekligi")}
              testID="kabin-kalibrasyonu-plaka-yuksekligi"
            />
          </View>
          <TouchableOpacity
            style={[styles.dugme, (konumlar.length < 2 || mesgul) && styles.kilitli]}
            onPress={() => void hesapla()}
            disabled={konumlar.length < 2 || mesgul}
            accessibilityRole="button"
            testID="kabin-kalibrasyonu-hesapla"
          >
            {mesgul ? <ActivityIndicator color="#fff" /> : <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.hesapla")}</Text>}
          </TouchableOpacity>
        </View>
      ) : null}

      {sonuc ? (
        <View style={styles.sonuc} testID="kabin-kalibrasyonu-sonuc">
          <Text style={[styles.durum, sonuc.gecerli ? styles.iyi : styles.uyari]}>
            {sonuc.gecerli ? t("ai.kalibrasyon.sonuc.gecerli") : t("ai.kalibrasyon.sonuc.gecersiz")}
          </Text>
          {sonuc.izdusumHatasiPx != null ? (
            <Text style={styles.not} testID="kabin-kalibrasyonu-izdusum">
              {t("ai.kalibrasyon.sonuc.izdusum", { px: sonuc.izdusumHatasiPx.toFixed(2), esik: sonuc.esikler.izdusumPx })}
            </Text>
          ) : null}
          {sonuc.olcumUyumuMm != null ? (
            <Text style={styles.not} testID="kabin-kalibrasyonu-uyum">
              {t("ai.kalibrasyon.sonuc.uyum", { mm: sonuc.olcumUyumuMm.toFixed(1), esik: sonuc.esikler.olcumMm, cm: cm(sonuc.yayilimCm) })}
            </Text>
          ) : null}
          {sonuc.konumlar.map((k, i) => (
            <Text key={i} style={styles.not} testID={`kabin-kalibrasyonu-sapma-${i}`}>
              {t("ai.kalibrasyon.sonuc.konumSapma", {
                n: i + 1,
                liste: k.koseSapmasiMm.map((v, j) => (v == null ? `${j + 1}: —` : `${j + 1}: ${v.toFixed(0)}`)).join(" · "),
              })}
            </Text>
          ))}
          {sonuc.caprazDogrulamaCm ? (
            <Text style={styles.not} testID="kabin-kalibrasyonu-capraz">
              {t("ai.kalibrasyon.sonuc.capraz", { liste: sonuc.caprazDogrulamaCm.map((v) => cm(v)).join(" / ") })}
            </Text>
          ) : null}
          {sonuc.hesaplananLensCm ? (
            <Text style={[styles.not, sonuc.lensUyarisi && styles.uyari]} testID="kabin-kalibrasyonu-lens">
              {sonuc.olculenLensCm
                ? t("ai.kalibrasyon.sonuc.lens", {
                    h: sonuc.hesaplananLensCm.map((v) => v.toFixed(1)).join(" / "),
                    o: sonuc.olculenLensCm.map((v) => v.toFixed(1)).join(" / "),
                    yatay: cm(sonuc.lensYatayFarkiCm),
                    dikey: cm(sonuc.lensDikeyFarkiCm),
                  })
                : t("ai.kalibrasyon.sonuc.lensOlcumsuz", { h: sonuc.hesaplananLensCm.map((v) => v.toFixed(1)).join(" / ") })}
            </Text>
          ) : null}
          {sonuc.gorusAlani?.onCm != null ? (
            <Text style={styles.not} testID="kabin-kalibrasyonu-sonuc-gorus">
              {t("ai.kalibrasyon.gorusAlani", { on: cm(sonuc.gorusAlani.onCm) })}
            </Text>
          ) : null}
          {sonuc.sahne && !sonuc.sahne.denetim ? <Text style={[styles.not, styles.uyari]}>{t("ai.kalibrasyon.sahneYok")}</Text> : null}
          {sonuc.nedenler.map((n) => (
            <Text key={n.kod} style={[styles.not, styles.uyari]} testID={`kabin-kalibrasyonu-neden-${n.kod}`}>
              • {n.metin}
            </Text>
          ))}
          {sonuc.gecerli && sonuc.lensUyarisi ? (
            <View style={styles.satir}>
              <Switch value={lensOnay} onValueChange={setLensOnay} testID="kabin-kalibrasyonu-lens-onay" />
              <Text style={[styles.not, styles.uyari]}>{t("ai.kalibrasyon.sonuc.lensOnay")}</Text>
            </View>
          ) : null}
          {sonuc.gecerli ? (
            <TouchableOpacity
              style={[styles.dugme, (mesgul || (sonuc.lensUyarisi && !lensOnay)) && styles.kilitli]}
              onPress={() => void kaydet()}
              disabled={mesgul || (sonuc.lensUyarisi && !lensOnay)}
              accessibilityRole="button"
              testID="kabin-kalibrasyonu-kaydet"
            >
              <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.kaydet")}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      {dogrulama ? (
        <Text style={[styles.durum, dogrulama.gecti ? styles.iyi : styles.uyari]} testID="kabin-kalibrasyonu-dogrulama-sonuc">
          {dogrulama.gecti
            ? t("ai.kalibrasyon.dogrulamaGecti", {
                merkez: dogrulama.merkezFarkCm.toFixed(1),
                farklar: dogrulama.farkCm.map((v, i) => (v == null ? null : `${i + 1}: ${v.toFixed(1)}`)).filter(Boolean).join(" · "),
                esik: dogrulama.esikCm,
              })
            : t("ai.kalibrasyon.dogrulamaKaldi", {
                merkez: dogrulama.merkezFarkCm.toFixed(1),
                farklar: dogrulama.farkCm.map((v, i) => (v == null ? null : `${i + 1}: ${v.toFixed(1)}`)).filter(Boolean).join(" · "),
                esik: dogrulama.esikCm,
              })}
        </Text>
      ) : null}

      {durum?.gecerli ? (
        <View style={styles.adimlar} testID="kabin-kalibrasyonu-taban">
          <Text style={styles.altBaslik}>{t("ai.kalibrasyon.taban.baslik")}</Text>
          {durum.olculenLensTabanCm != null ? (
            <>
              <Text style={styles.not}>{t("ai.kalibrasyon.taban.aciklama", { lens: cm(durum.olculenLensTabanCm) })}</Text>
              <View style={styles.satir}>
                <TextInput
                  style={styles.giris}
                  keyboardType="decimal-pad"
                  value={tabanUzaklik}
                  onChangeText={setTabanUzaklik}
                  placeholder={t("ai.kalibrasyon.taban.uzaklik")}
                  accessibilityLabel={t("ai.kalibrasyon.taban.uzaklik")}
                  editable={!kilitli}
                  testID="kabin-kalibrasyonu-taban-uzaklik"
                />
                <TouchableOpacity
                  style={[styles.dugme, (kilitli || mesgul || !gecerliSayi(tabanUzaklik)) && styles.kilitli]}
                  onPress={() => void tabanUygula()}
                  disabled={kilitli || mesgul || !gecerliSayi(tabanUzaklik)}
                  accessibilityRole="button"
                  testID="kabin-kalibrasyonu-taban-uygula"
                >
                  <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.taban.uygula")}</Text>
                </TouchableOpacity>
              </View>
              <Text style={styles.not} testID="kabin-kalibrasyonu-taban-durum">
                {t("ai.kalibrasyon.taban.durum", { cm: cm(durum.tabanYukseltmesiCm ?? 0) })}
              </Text>
            </>
          ) : (
            <Text style={[styles.not, styles.uyari]}>{t("ai.kalibrasyon.taban.lensYok")}</Text>
          )}
        </View>
      ) : null}

      {durum?.gecerli ? (
        <View style={styles.adimlar} testID="kabin-kalibrasyonu-devam">
          <Text style={styles.altBaslik}>{t("ai.kalibrasyon.devam.baslik")}</Text>
          <Text style={styles.not}>{t("ai.kalibrasyon.devam.aciklama")}</Text>
          <TouchableOpacity
            style={[styles.dugme, styles.ikincil, (kilitli || mesgul) && styles.kilitli]}
            onPress={() => void devamEt()}
            disabled={kilitli || mesgul}
            accessibilityRole="button"
            testID="kabin-kalibrasyonu-devam-et"
          >
            <Text style={[styles.dugmeMetni, styles.ikincilMetin]}>{t("ai.kalibrasyon.devam.dugme")}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {model === "fantom" && durum?.gecerli ? (
        <View style={styles.adimlar} testID="kabin-kalibrasyonu-fantom">
          <Text style={styles.altBaslik}>{t("ai.kalibrasyon.fantom.baslik")}</Text>
          <Text style={styles.not}>{t("ai.kalibrasyon.fantom.aciklama")}</Text>
          <View style={styles.satir}>
            {(
              [
                ["kalinlik", t("ai.kalibrasyon.fantom.kalinlik")],
                ["derinlik", t("ai.kalibrasyon.fantom.derinlik")],
                ["boy", t("ai.kalibrasyon.fantom.boy")],
                ["en", t("ai.kalibrasyon.fantom.en")],
              ] as const
            ).map(([a, etiket]) => (
              <TextInput
                key={a}
                style={styles.giris}
                keyboardType="decimal-pad"
                value={fantom[a]}
                onChangeText={(s) => setFantom((p) => ({ ...p, [a]: s }))}
                placeholder={etiket}
                accessibilityLabel={etiket}
                editable={!kilitli}
                testID={`kabin-kalibrasyonu-fantom-${a}`}
              />
            ))}
          </View>
          <TouchableOpacity
            style={[styles.dugme, (kilitli || mesgul || !gecerliSayi(fantom.kalinlik)) && styles.kilitli]}
            onPress={() => void fantomKaydet()}
            disabled={kilitli || mesgul || !gecerliSayi(fantom.kalinlik)}
            accessibilityRole="button"
            testID="kabin-kalibrasyonu-fantom-kaydet"
          >
            <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.fantom.kaydet")}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {mesaj ? (
        <Text style={styles.durum} testID="kabin-kalibrasyonu-mesaj">
          {mesaj}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  kutu: {
    marginVertical: spacing.sm,
    gap: spacing.sm,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  satir: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  baslik: { fontSize: typography.body, fontWeight: "700", color: colors.text },
  altBaslik: { fontSize: typography.small, fontWeight: "700", color: colors.text, marginTop: spacing.sm },
  aciklama: { fontSize: typography.small, color: colors.textMuted },
  not: { fontSize: typography.small, color: colors.textMuted },
  durum: { fontSize: typography.small, color: colors.text },
  uyari: { color: colors.danger },
  dikkat: { color: colors.warning },
  iyi: { color: colors.success },
  dugme: {
    minHeight: touch.min,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  ikincil: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.primary },
  ikincilMetin: { color: colors.primary },
  dugmeMetni: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  kilitli: { opacity: 0.5 },
  adimlar: { gap: spacing.sm },
  koseSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", padding: spacing.xs, borderRadius: radius.sm },
  koseAdi: { fontSize: typography.small, fontWeight: "700", color: colors.text, minWidth: 90 },
  giris: {
    minWidth: 110,
    minHeight: touch.min,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    color: colors.text,
  },
  baglanti: { color: colors.primary, fontSize: typography.small, fontWeight: "700" },
  sonuc: { gap: spacing.xs },
});
