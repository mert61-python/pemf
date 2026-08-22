// Author: mertaygn, cglrgrkn
/**
 * SÜRÜM FARKI BANDI (sahip kararı 2026-08-22).
 *
 * NEDEN. Telefon uygulaması cihazdan FARKLI bir sürümde kalabilir ve bu KASITLIDIR: Android'de
 * kurulumu işletim sistemi sorar; kullanıcı reddedebilir, "bilinmeyen kaynak" izni hiç verilmemiş
 * olabilir, kurumsal profil yasaklamış olabilir. Bu yüzden güncelleme ZORUNLU KILINAMAZ ve
 * bağlantı sürüm uyuşmazlığında ASLA reddedilmez — bir tıbbi cihazın uzaktan ACİL DURDURMASINI
 * sürüm eşleşmesine bağlamak kabul edilemez (bkz. MobileUpdateGate).
 *
 * AMA "sessizce eksik" de kabul edilemezdi. Ölçüldü: bu sürümde eklenen düzeltmelerin bir kısmı
 * İSTEMCİ tarafındadır (gözlem notunun hasta kimliğine bağlanması, yükleyicinin çalışan bobini
 * görmesi, keşifteki cihaz-kimliği yan etkisi). Eski telefonda bunlar YOKTUR ve kullanıcı bunu
 * hiçbir yerden anlayamıyordu — ekran normal görünüyordu.
 *
 * Bu bant o boşluğu görünür kılar. ⚠️ BLOKLAMAZ: kapatılabilir, girişi engellemez, acil durdurma
 * yolunu hiç etkilemez. Bir hız kesici bile değil — yalnızca bir bilgi.
 *
 * ⚠️ HASTA GÜVENLİĞİ: seans sürerken GÖSTERİLMEZ. Bobinler hastanın üzerindeyken operatörün
 * ekranını yönetimsel bir uyarıyla bölmek kabul edilemez (RecoveryCodeBanner ile aynı ilke).
 *
 * ⚠️ SÜRÜM NUMARALARI AYRI ŞEMADIR: telefon 2.3.x, cihaz 1.9.x. "Eşit olmalı" diye bir kural
 * YOKTUR — bant yalnızca ikisini yan yana gösterir ve güncelleme öner; hangisinin "ileri"
 * olduğuna dair bir karşılaştırma YAPMAZ (yapamaz da).
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Info, X } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { useLiveData } from "@/context/LiveDataContext";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

/** Kapatma, GÖRÜLEN sürüm çiftine bağlıdır: cihaz güncellenince bant yeniden çıkar. */
const ANAHTAR = "pemf.surumFarki.kapatilan";

function uygulamaSurumu(): string {
  try {
    // @ts-ignore - expo-constants opsiyonel
    return require("expo-constants").default?.expoConfig?.version || "";
  } catch {
    return "";
  }
}

export function SurumFarkiBanner() {
  const { snapshot, haveRealData } = useLiveData();
  const cihaz = snapshot.system?.softwareVersion ?? "";
  const uygulama = uygulamaSurumu();
  const seansSuruyor = Boolean(snapshot.activeTreatment?.isActive);
  const [kapatilan, setKapatilan] = useState<string | null>(null);
  const [yuklendi, setYuklendi] = useState(false);

  const cift = `${uygulama}|${cihaz}`;

  useEffect(() => {
    let iptal = false;
    AsyncStorage.getItem(ANAHTAR)
      .then((v) => {
        if (!iptal) {
          setKapatilan(v);
          setYuklendi(true);
        }
      })
      .catch(() => {
        // Depolama okunamazsa bandı GÖSTER (bilgiyi gizlemektense göstermek doğrudur).
        if (!iptal) setYuklendi(true);
      });
    return () => {
      iptal = true;
    };
  }, []);

  // Gerçek veri yoksa cihaz sürümü bilinmiyordur → sahte "fark var" uyarısı üretme.
  if (!yuklendi || !haveRealData || !cihaz || !uygulama) return null;
  if (seansSuruyor) return null;
  if (kapatilan === cift) return null;

  return (
    <View style={s.kutu}>
      <Info size={rs(16)} color={colors.primary} />
      <View style={s.metin}>
        <Text style={s.baslik}>
          Telefon {uygulama} · cihaz {cihaz}
        </Text>
        <Text style={s.aciklama}>
          Sürümler farklı. Bağlantı ve acil durdurma normal çalışır; ancak bu telefonda bazı
          düzeltmeler ve uyarılar eksik olabilir. Ayarlar’dan güncelleyebilirsiniz.
        </Text>
      </View>
      <TouchableOpacity
        onPress={() => {
          setKapatilan(cift);
          AsyncStorage.setItem(ANAHTAR, cift).catch(() => {});
        }}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        accessibilityLabel="Sürüm farkı bildirimini kapat"
      >
        <X size={rs(16)} color={colors.textMuted} />
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  kutu: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.panelSoft,
    borderWidth: 1,
    borderColor: colors.border,
  },
  metin: { flex: 1 },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "600" },
  aciklama: { color: colors.textMuted, fontSize: rf(11), marginTop: 2, lineHeight: rf(15) },
});
