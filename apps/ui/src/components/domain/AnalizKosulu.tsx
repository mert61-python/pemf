// Author: mertaygn, cglrgrkn
/**
 * ANALİZ KOŞULU + KABİN KAMERASI (T3 · Y189, sahip + Çağlar Hoca 2026-10-23).
 *
 * `KosulSecici` — "Koşullu | Koşulsuz": "engelleri tamamen kaldırdığın bir sürüm, butonla kontrol edilebilir; AI tek başına ne
 * bulacak". Petri / fantom analizinde ve AI Pro'da (araştırma modelleri) AYNI bileşen. Varsayılan KOŞULLU, seçim HATIRLANMAZ
 * (her açılışta koşullu). Kural backend'dedir (`ai_hub/cv_ortak/pemf_kapisi.py` + petri v2 hattı): koşulsuzda engeller analizi /
 * sürüşü KESMEZ, uyarı olarak gösterilir; kabin çerçevesinde konum yoksa yine sürülmez. Bileşen yalnız seçimi taşır.
 *
 * KABİN KAMERASI (T3 · Y190, sahip 2026-10-24: "fotoğraf çek direkt kabin kamerasından çekmeliydi … kabin kamerasından çek gereksiz
 * buton"): Y189'un ayrı "Kabin kamerasından çek" düğmesi KALKTI. Bu makinede (`kabinKamerasiKullanilir`: web + yerel backend —
 * masaüstü / LattePanda) petri / fantom "Fotoğraf Çek" DOĞRUDAN seçili kabin kamerasından 1920×1080 alır (`kabinKaresiAl` →
 * `POST /api/settings/kabin-kamerasi/kare`; kalibrasyonla aynı çözünürlük), "Canlı Kamera" backend canlı oturumunu kullanır
 * (`kabinCanli*`). Telefonda / uzak tarayıcıda cihazın kendi kamerası (kamera backend'in makinesine bağlıdır). Hata metni sunucudan
 * gelir ve EYLEM söyler (`KabinKamerasiHatasi`).
 */
import React from "react";
import { Platform, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import i18n from "i18next";

import { authHeaders } from "@/services/apiClient";
import { backendBuMakinede } from "@/services/backendKonumu";
import { serviceConfig } from "@/services/config";
import { colors, touch, typography } from "@/theme/tokens";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";

export function KosulSecici({
  kosulsuz,
  onDegis,
  kilitli = false,
  testID = "kosul-secici",
}: {
  kosulsuz: boolean;
  onDegis: (kosulsuz: boolean) => void;
  kilitli?: boolean;
  testID?: string;
}) {
  const { t } = useTranslation();
  const secenekler: [boolean, string][] = [
    [false, t("ai.kosul.kosullu")],
    [true, t("ai.kosul.kosulsuz")],
  ];
  return (
    <View testID={testID} style={{ marginVertical: 6 }}>
      <View style={{ flexDirection: "row", gap: 8 }} accessibilityRole="radiogroup" accessibilityLabel={t("ai.kosul.etiket")}>
        {secenekler.map(([deger, etiket]) => {
          const secili = kosulsuz === deger;
          return (
            <TouchableOpacity
              key={String(deger)}
              testID={deger ? `${testID}-kosulsuz` : `${testID}-kosullu`}
              disabled={kilitli}
              onPress={() => onDegis(deger)}
              accessibilityRole="radio"
              accessibilityState={{ selected: secili, disabled: kilitli }}
              accessibilityLabel={etiket}
              style={{
                flex: 1,
                minHeight: touch.sm,
                justifyContent: "center",
                padding: 8,
                borderWidth: 1,
                borderRadius: 8,
                borderColor: secili ? (deger ? colors.warning : colors.primary) : colors.border,
                opacity: kilitli ? 0.5 : 1,
              }}
            >
              <Text style={{ fontSize: typography.small, fontWeight: secili ? "bold" : "normal", color: colors.text }}>
                {secili ? "◉" : "○"} {etiket}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text
        testID={`${testID}-aciklama`}
        style={{ fontSize: typography.small, marginTop: 4, color: kosulsuz ? colors.warning : colors.textMuted }}
      >
        {kosulsuz ? t("ai.kosul.kosulsuzUyari") : t("ai.kosul.kosulluAciklama")}
      </Text>
    </View>
  );
}

/** Analiz kamerası bu makinenin SEÇİLİ KABİN KAMERASI mı? Yalnız web + yerel backend (yerel uygulamada / uzak tarayıcıda kabin
 *  kamerası kullanıcının cihazına bağlı değildir → cihazın kendi kamerası). */
export function kabinKamerasiKullanilir(): boolean {
  return Platform.OS === "web" && backendBuMakinede();
}

/** Kabin kamerası ucunun hatası: `message` sunucunun EYLEM metni (yoksa genel metin), `durum` HTTP kodu (ağ hatasında 0). */
export class KabinKamerasiHatasi extends Error {
  durum: number;
  constructor(mesaj: string, durum: number) {
    super(mesaj);
    this.durum = durum;
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function kabinIstegi(yol: string, yontem: "GET" | "POST"): Promise<any> {
  let r: Response;
  try {
    r = await fetch(serviceConfig.apiBaseUrl + "/settings/kabin-kamerasi" + yol, {
      method: yontem,
      headers: { Accept: "application/json", ...authHeaders() },
    });
  } catch {
    throw new KabinKamerasiHatasi(i18n.t("ai.kabinKamerasi.hata"), 0);
  }
  const j = await r.json().catch(() => null);
  if (!r.ok) throw new KabinKamerasiHatasi(aiDetayCumlesi(j?.detail, i18n.t("ai.kabinKamerasi.hata")), r.status);
  return j;
}

/** "Fotoğraf Çek" (bu makinede): seçili kabin kamerasından 1920×1080 tek kare (base64 JPEG). */
export async function kabinKaresiAl(): Promise<string> {
  const j = await kabinIstegi("/kare", "POST");
  if (!j?.image_base64) throw new KabinKamerasiHatasi(i18n.t("ai.kabinKamerasi.hata"), 0);
  return String(j.image_base64);
}

/** Canlı oturum: kamera backend'de AÇIK tutulur (kare istenmezse kendiliğinden kapanır — `kabin_kamerasi.CANLI_ZAMAN_ASIMI_SN`). */
export async function kabinCanliBaslat(): Promise<void> {
  await kabinIstegi("/canli/baslat", "POST");
}

/** Canlı oturumun son karesi: `tam` = kalibrasyon boyutunda (analiz), değilse küçük önizleme. Oturum kapalıysa 409.
 *  T3 · Y192: oturum açık ama ilk kare henüz yoksa sunucu `hazir: false` ("bekliyor") döner → null (kapalı DEĞİL; sonraki turda yeniden
 *  istenir). Ölçülen HP kamerası: başlatma 0,3–0,5 sn, ilk kare ~0,5–1,8 sn sonra — eskiden bu arada canlı duruyordu. */
export async function kabinCanliKare(tam: boolean): Promise<string | null> {
  const j = await kabinIstegi(tam ? "/canli/kare?tam=true" : "/canli/kare", "GET");
  if (j?.hazir === false) return null;
  if (!j?.image_base64) throw new KabinKamerasiHatasi(i18n.t("ai.kabinKamerasi.hata"), 0);
  return String(j.image_base64);
}

/** Canlı oturumu kapatır (kamera bırakılır); hata yutulur — oturum zaten zaman aşımıyla da kapanır. */
export async function kabinCanliDurdur(): Promise<void> {
  try {
    await kabinIstegi("/canli/durdur", "POST");
  } catch {
    /* zaman aşımı yine kapatır */
  }
}
