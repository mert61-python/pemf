/**
 * KABİN KALİBRASYONU (KD · sahip kararları Y258–Y260, 2026-11-10) — sabit düzlem kalibrasyonu ekranı. Araştırma profili, AI Pro panelinde
 * petri / fantom modeliyle; masaüstü + telefon + web (kare ARKA UÇTAKİ kabin kamerasından gelir — telefon da aynı uçları kullanır).
 *
 * Akış: kare al → plakanın 4 ÜST dış köşesine sırayla dokun (ön-sol, ön-sağ, arka-sağ, arka-sol; büyüteç + 1 px ince ayar) → köşe başına
 * sol / ön cama uzaklık (cm) + lens konumu (sol / ön / taban camından, cm) → Hesapla (yeniden izdüşüm, hesaplanan ↔ ölçülen lens, kuyu
 * aralığı) → Kaydet (lens farkı 2 cm'yi aşarsa AÇIK onay ister; kayıt denetim izine). "Doğrula": plaka başka yerde, 2 köşe → fark cm.
 * Fantom: kalınlık / tümör derinliği / boy (sahip ölçer). Bütün metinler sunucunun ya da kataloğun (TR + EN); arayüz kural UYDURMAZ —
 * geçerlilik, eşikler ve nedenler arka uçtan (`/api/ai/pro/kalibrasyon/*`).
 */
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Crosshair } from "lucide-react-native";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { AI_TIMEOUT_MS, apiGet, apiPost, KAMERA_TIMEOUT_MS } from "@/services/apiClient";

type Kip = "kalibrasyon" | "dogrulama";
interface Kare {
  kareKimligi: string;
  genislik: number;
  yukseklik: number;
  image_base64: string;
}
interface Nokta {
  u: number;
  v: number;
}
interface Durum {
  var: boolean;
  gecerli: boolean;
  hataMetni?: string;
  tarih?: string;
  izdusumHatasiPx?: number;
  lensFarkiCm?: number | null;
  sahneDenetimi?: boolean;
  fantom?: { kalinlikCm: number | null; tumorDerinligiCm: number | null; boyCm: (number | null)[] | null };
  sonDogrulama?: { maks_cm: number; gecti: boolean } | null;
}
interface Sonuc {
  gecerli: boolean;
  nedenler: { kod: string; metin: string }[];
  izdusumHatasiPx: number | null;
  hesaplananLensCm: number[] | null;
  olculenLensCm: number[] | null;
  lensFarkiCm: number | null;
  lensUyarisi: boolean;
  kuyuAraligi: { sutunMm: number; satirMm: number; beklenenMm: number; sapma: number; gecti: boolean } | null;
  sahne: { oznitelik: number; denetim: boolean } | null;
  esikler: { izdusumPx: number; lensCm: number };
}
interface Dogrulama {
  farkCm: number[];
  maksCm: number;
  gecti: boolean;
  esikCm: number;
}

const BUYUTEC = 180;
const BUYUTME = 4;

const sayi = (s: string) => Number(String(s).replace(",", "."));
const gecerliSayi = (s: string) => s.trim() !== "" && Number.isFinite(sayi(s));

export function KabinKalibrasyonuKarti({ model, kilitli = false }: { model: "petri" | "fantom"; kilitli?: boolean }) {
  const { t } = useTranslation();
  const [durum, setDurum] = useState<Durum | null>(null);
  const [kip, setKip] = useState<Kip | null>(null);
  const [kare, setKare] = useState<Kare | null>(null);
  const [aliniyor, setAliniyor] = useState(false);
  const [noktalar, setNoktalar] = useState<(Nokta | null)[]>([]);
  const [aktif, setAktif] = useState(0);
  const [olcum, setOlcum] = useState<{ sol: string; on: string }[]>([]);
  const [lens, setLens] = useState({ sol: "", on: "", taban: "" });
  const [plakaYuk, setPlakaYuk] = useState("2");
  const [sonuc, setSonuc] = useState<Sonuc | null>(null);
  const [lensOnay, setLensOnay] = useState(false);
  const [dogrulama, setDogrulama] = useState<Dogrulama | null>(null);
  const [mesaj, setMesaj] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const [genislik, setGenislik] = useState(0);
  const [fantom, setFantom] = useState({ kalinlik: "", derinlik: "", boy: "", en: "" });

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

  const baslat = async (yeni: Kip) => {
    if (kilitli || aliniyor) return;
    setKip(yeni);
    setSonuc(null);
    setDogrulama(null);
    setMesaj(null);
    setLensOnay(false);
    const n = yeni === "kalibrasyon" ? 4 : 2;
    setNoktalar(Array(n).fill(null));
    setOlcum(Array.from({ length: n }, () => ({ sol: "", on: "" })));
    setAktif(0);
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

  const gosterim = kare ? { w: Math.min(genislik || 320, 960), h: (Math.min(genislik || 320, 960) * kare.yukseklik) / kare.genislik } : null;

  const dokun = (x: number, y: number) => {
    if (!kare || !gosterim || aktif >= noktalar.length) return;
    const u = Math.round((x * kare.genislik) / gosterim.w);
    const v = Math.round((y * kare.yukseklik) / gosterim.h);
    setNoktalar((p) => p.map((q, i) => (i === aktif ? { u, v } : q)));
    setSonuc(null);
  };

  const kaydir = (du: number, dv: number) => {
    if (!kare) return;
    setNoktalar((p) =>
      p.map((q, i) =>
        i === aktif && q
          ? { u: Math.min(kare.genislik, Math.max(0, q.u + du)), v: Math.min(kare.yukseklik, Math.max(0, q.v + dv)) }
          : q
      )
    );
    setSonuc(null);
  };

  // Köşe sırası arka uçla AYNI (`sabit_duzlem.KOSE_ADLARI`): ön-sol, ön-sağ, arka-sağ, arka-sol.
  const koseAdlari = [
    t("ai.kalibrasyon.kose.onSol"),
    t("ai.kalibrasyon.kose.onSag"),
    t("ai.kalibrasyon.kose.arkaSag"),
    t("ai.kalibrasyon.kose.arkaSol"),
  ];
  const koseAdi = (i: number) => (kip === "dogrulama" ? t("ai.kalibrasyon.kose.dogrulama", { sira: i + 1 }) : koseAdlari[i]);
  const tamam = kare !== null && noktalar.length > 0 && noktalar.every(Boolean) && olcum.every((o) => gecerliSayi(o.sol) && gecerliSayi(o.on));
  const lensVar = gecerliSayi(lens.sol) && gecerliSayi(lens.on) && gecerliSayi(lens.taban);

  const govde = () => ({
    kareKimligi: kare?.kareKimligi,
    koseler: noktalar.map((n, i) => ({ u: n?.u, v: n?.v, solCm: sayi(olcum[i].sol), onCm: sayi(olcum[i].on) })),
    lens: lensVar ? { solCm: sayi(lens.sol), onCm: sayi(lens.on), tabanCm: sayi(lens.taban) } : null,
    plakaYuksekligiCm: sayi(plakaYuk),
    lensUyarisiniOnayla: lensOnay,
  });

  const hesapla = async () => {
    if (!tamam || mesgul) return;
    setMesgul(true);
    setMesaj(null);
    try {
      const r = await apiPost<Sonuc | null>("/ai/pro/kalibrasyon/hesapla", govde(), null, {
        timeoutMs: AI_TIMEOUT_MS,
        silent: true,
        onHttpError: hataYakala,
      });
      if (r) setSonuc(r);
    } finally {
      setMesgul(false);
    }
  };

  const kaydet = async () => {
    if (!tamam || mesgul || !sonuc?.gecerli || (sonuc.lensUyarisi && !lensOnay)) return;
    setMesgul(true);
    setMesaj(null);
    try {
      const r = await apiPost<{ durum: Durum } | null>("/ai/pro/kalibrasyon/kaydet", govde(), null, {
        timeoutMs: AI_TIMEOUT_MS,
        silent: true,
        onHttpError: hataYakala,
      });
      if (r?.durum) {
        setDurum(r.durum);
        setMesaj(t("ai.kalibrasyon.kaydedildi"));
        setKip(null);
        setKare(null);
      }
    } finally {
      setMesgul(false);
    }
  };

  const dogrula = async () => {
    if (!tamam || mesgul) return;
    setMesgul(true);
    setMesaj(null);
    try {
      const b = govde();
      const r = await apiPost<Dogrulama | null>(
        "/ai/pro/kalibrasyon/dogrula",
        { kareKimligi: b.kareKimligi, koseler: b.koseler },
        null,
        { timeoutMs: AI_TIMEOUT_MS, silent: true, onHttpError: hataYakala }
      );
      if (r) {
        setDogrulama(r);
        void yukle();
      }
    } finally {
      setMesgul(false);
    }
  };

  const fantomKaydet = async () => {
    if (mesgul || !gecerliSayi(fantom.kalinlik)) return;
    setMesgul(true);
    setMesaj(null);
    try {
      const boyVar = gecerliSayi(fantom.boy) && gecerliSayi(fantom.en);
      const r = await apiPost<{ durum: Durum } | null>(
        "/ai/pro/kalibrasyon/fantom",
        {
          kalinlikCm: sayi(fantom.kalinlik),
          tumorDerinligiCm: gecerliSayi(fantom.derinlik) ? sayi(fantom.derinlik) : 0,
          boyCm: boyVar ? sayi(fantom.boy) : null,
          enCm: boyVar ? sayi(fantom.en) : null,
        },
        null,
        { silent: true, onHttpError: hataYakala }
      );
      if (r?.durum) {
        setDurum(r.durum);
        setMesaj(t("ai.kalibrasyon.fantom.kaydedildi"));
      }
    } finally {
      setMesgul(false);
    }
  };

  const secili = noktalar[aktif] ?? null;

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
              px: (durum.izdusumHatasiPx ?? 0).toFixed(2),
              cm: durum.lensFarkiCm == null ? "—" : durum.lensFarkiCm.toFixed(1),
            })}
          </Text>
        ) : (
          <Text style={[styles.durum, styles.uyari]} testID="kabin-kalibrasyonu-durum">
            {durum.hataMetni ?? t("ai.kalibrasyon.durumYok")}
          </Text>
        )
      ) : null}
      {durum?.gecerli && durum.sahneDenetimi === false ? (
        <Text style={[styles.not, styles.uyari]} testID="kabin-kalibrasyonu-sahne-yok">
          {t("ai.kalibrasyon.sahneYok")}
        </Text>
      ) : null}

      <View style={styles.satir}>
        <TouchableOpacity
          style={[styles.dugme, (kilitli || aliniyor) && styles.kilitli]}
          onPress={() => void baslat("kalibrasyon")}
          disabled={kilitli || aliniyor}
          accessibilityRole="button"
          testID="kabin-kalibrasyonu-baslat"
        >
          <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.kalibreEt")}</Text>
        </TouchableOpacity>
        {durum?.gecerli ? (
          <TouchableOpacity
            style={[styles.dugme, styles.ikincil, (kilitli || aliniyor) && styles.kilitli]}
            onPress={() => void baslat("dogrulama")}
            disabled={kilitli || aliniyor}
            accessibilityRole="button"
            testID="kabin-kalibrasyonu-dogrula-baslat"
          >
            <Text style={[styles.dugmeMetni, styles.ikincilMetin]}>{t("ai.kalibrasyon.dogrula")}</Text>
          </TouchableOpacity>
        ) : null}
      </View>
      {kilitli ? <Text style={styles.not}>{t("ai.kalibrasyon.kilitli")}</Text> : null}
      {aliniyor ? (
        <View style={styles.satir} testID="kabin-kalibrasyonu-kare-aliniyor">
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.not}>{t("ai.kalibrasyon.kareAliniyor")}</Text>
        </View>
      ) : null}

      {kip && kare && gosterim ? (
        <View style={styles.adimlar}>
          <Text style={styles.not}>{kip === "kalibrasyon" ? t("ai.kalibrasyon.dokunAciklama") : t("ai.kalibrasyon.dogrulaAciklama")}</Text>
          <Pressable
            onPress={(e) => dokun(e.nativeEvent.locationX, e.nativeEvent.locationY)}
            style={{ width: gosterim.w, height: gosterim.h }}
            testID="kabin-kalibrasyonu-kare"
            accessibilityLabel={t("ai.kalibrasyon.kareEtiketi")}
          >
            <Image source={{ uri: `data:image/jpeg;base64,${kare.image_base64}` }} style={{ width: gosterim.w, height: gosterim.h }} />
            {noktalar.map((n, i) =>
              n ? (
                <View
                  key={i}
                  pointerEvents="none"
                  style={[
                    styles.isaret,
                    i === aktif && styles.isaretAktif,
                    { left: (n.u * gosterim.w) / kare.genislik - 7, top: (n.v * gosterim.h) / kare.yukseklik - 7 },
                  ]}
                />
              ) : null
            )}
          </Pressable>

          {secili ? (
            <View style={styles.satir}>
              <View style={styles.buyutec} testID="kabin-kalibrasyonu-buyutec" pointerEvents="none">
                <Image
                  source={{ uri: `data:image/jpeg;base64,${kare.image_base64}` }}
                  style={{
                    position: "absolute",
                    width: gosterim.w * BUYUTME,
                    height: gosterim.h * BUYUTME,
                    left: BUYUTEC / 2 - ((secili.u * gosterim.w) / kare.genislik) * BUYUTME,
                    top: BUYUTEC / 2 - ((secili.v * gosterim.h) / kare.yukseklik) * BUYUTME,
                  }}
                />
                <View style={[styles.arti, { width: 1, height: BUYUTEC, left: BUYUTEC / 2 }]} />
                <View style={[styles.arti, { height: 1, width: BUYUTEC, top: BUYUTEC / 2 }]} />
              </View>
              <View style={styles.okKutusu}>
                <Text style={styles.not}>{t("ai.kalibrasyon.inceAyar")}</Text>
                <View style={styles.satir}>
                  {[
                    { ad: "sol", du: -1, dv: 0, Ikon: ChevronLeft, etiket: t("ai.kalibrasyon.yon.sol") },
                    { ad: "yukari", du: 0, dv: -1, Ikon: ChevronUp, etiket: t("ai.kalibrasyon.yon.yukari") },
                    { ad: "asagi", du: 0, dv: 1, Ikon: ChevronDown, etiket: t("ai.kalibrasyon.yon.asagi") },
                    { ad: "sag", du: 1, dv: 0, Ikon: ChevronRight, etiket: t("ai.kalibrasyon.yon.sag") },
                  ].map(({ ad, du, dv, Ikon, etiket }) => (
                    <TouchableOpacity
                      key={ad}
                      style={styles.ok}
                      onPress={() => kaydir(du, dv)}
                      accessibilityRole="button"
                      accessibilityLabel={etiket}
                      testID={`kabin-kalibrasyonu-ok-${ad}`}
                    >
                      <Ikon color={colors.text} size={18} />
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>
          ) : null}

          {noktalar.map((n, i) => (
            <View key={i} style={[styles.koseSatiri, i === aktif && styles.koseAktif]} testID={`kabin-kalibrasyonu-kose-${i}`}>
              <TouchableOpacity onPress={() => setAktif(i)} accessibilityRole="button" testID={`kabin-kalibrasyonu-kose-sec-${i}`}>
                <Text style={styles.koseAdi}>
                  {i + 1}. {koseAdi(i)}
                </Text>
                <Text style={styles.not}>{n ? t("ai.kalibrasyon.piksel", { u: n.u, v: n.v }) : t("ai.kalibrasyon.dokunulmadi")}</Text>
              </TouchableOpacity>
              <TextInput
                style={styles.giris}
                keyboardType="decimal-pad"
                value={olcum[i]?.sol ?? ""}
                onChangeText={(s) => setOlcum((p) => p.map((o, j) => (j === i ? { ...o, sol: s } : o)))}
                placeholder={t("ai.kalibrasyon.solCm")}
                accessibilityLabel={`${koseAdi(i)} ${t("ai.kalibrasyon.solCm")}`}
                testID={`kabin-kalibrasyonu-sol-${i}`}
              />
              <TextInput
                style={styles.giris}
                keyboardType="decimal-pad"
                value={olcum[i]?.on ?? ""}
                onChangeText={(s) => setOlcum((p) => p.map((o, j) => (j === i ? { ...o, on: s } : o)))}
                placeholder={t("ai.kalibrasyon.onCm")}
                accessibilityLabel={`${koseAdi(i)} ${t("ai.kalibrasyon.onCm")}`}
                testID={`kabin-kalibrasyonu-on-${i}`}
              />
            </View>
          ))}
          {noktalar[aktif] && aktif < noktalar.length - 1 ? (
            <TouchableOpacity onPress={() => setAktif(aktif + 1)} accessibilityRole="button" testID="kabin-kalibrasyonu-sonraki">
              <Text style={styles.baglanti}>{t("ai.kalibrasyon.sonrakiKose", { kose: koseAdi(aktif + 1) })}</Text>
            </TouchableOpacity>
          ) : null}

          {kip === "kalibrasyon" ? (
            <>
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
                style={[styles.dugme, (!tamam || mesgul) && styles.kilitli]}
                onPress={() => void hesapla()}
                disabled={!tamam || mesgul}
                accessibilityRole="button"
                testID="kabin-kalibrasyonu-hesapla"
              >
                {mesgul ? <ActivityIndicator color="#fff" /> : <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.hesapla")}</Text>}
              </TouchableOpacity>
            </>
          ) : (
            <TouchableOpacity
              style={[styles.dugme, (!tamam || mesgul) && styles.kilitli]}
              onPress={() => void dogrula()}
              disabled={!tamam || mesgul}
              accessibilityRole="button"
              testID="kabin-kalibrasyonu-dogrula"
            >
              {mesgul ? <ActivityIndicator color="#fff" /> : <Text style={styles.dugmeMetni}>{t("ai.kalibrasyon.dogrulaHesapla")}</Text>}
            </TouchableOpacity>
          )}
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
          {sonuc.hesaplananLensCm ? (
            <Text style={[styles.not, sonuc.lensUyarisi && styles.uyari]} testID="kabin-kalibrasyonu-lens">
              {sonuc.olculenLensCm
                ? t("ai.kalibrasyon.sonuc.lens", {
                    h: sonuc.hesaplananLensCm.map((v) => v.toFixed(1)).join(" / "),
                    o: sonuc.olculenLensCm.map((v) => v.toFixed(1)).join(" / "),
                    cm: (sonuc.lensFarkiCm ?? 0).toFixed(1),
                  })
                : t("ai.kalibrasyon.sonuc.lensOlcumsuz", { h: sonuc.hesaplananLensCm.map((v) => v.toFixed(1)).join(" / ") })}
            </Text>
          ) : null}
          <Text style={[styles.not, sonuc.kuyuAraligi && !sonuc.kuyuAraligi.gecti && styles.uyari]} testID="kabin-kalibrasyonu-kuyu">
            {sonuc.kuyuAraligi
              ? t("ai.kalibrasyon.sonuc.kuyu", {
                  sutun: sonuc.kuyuAraligi.sutunMm.toFixed(2),
                  satir: sonuc.kuyuAraligi.satirMm.toFixed(2),
                  beklenen: sonuc.kuyuAraligi.beklenenMm,
                  yuzde: (sonuc.kuyuAraligi.sapma * 100).toFixed(1),
                })
              : t("ai.kalibrasyon.sonuc.kuyuYok")}
          </Text>
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
            ? t("ai.kalibrasyon.dogrulamaGecti", { farklar: dogrulama.farkCm.map((v) => v.toFixed(1)).join(" / "), maks: dogrulama.maksCm.toFixed(1), esik: dogrulama.esikCm })
            : t("ai.kalibrasyon.dogrulamaKaldi", { farklar: dogrulama.farkCm.map((v) => v.toFixed(1)).join(" / "), maks: dogrulama.maksCm.toFixed(1), esik: dogrulama.esikCm })}
        </Text>
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
  isaret: { position: "absolute", width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: colors.warning },
  isaretAktif: { borderColor: colors.danger },
  buyutec: { width: BUYUTEC, height: BUYUTEC, overflow: "hidden", borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm },
  arti: { position: "absolute", backgroundColor: colors.danger },
  okKutusu: { gap: spacing.xs },
  ok: {
    minWidth: touch.min,
    minHeight: touch.min,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
  },
  koseSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", padding: spacing.xs, borderRadius: radius.sm },
  koseAktif: { backgroundColor: "rgba(59,130,246,0.08)" },
  koseAdi: { fontSize: typography.small, fontWeight: "700", color: colors.text },
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
