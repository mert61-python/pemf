// Author: mertaygn, cglrgrkn
/**
 * AI ÖNERİSİ ONAY MODALI (2026-08-06, sahip kararı: "sert kapı — onaysız tedavi başlamaz")
 *
 * AI Pro artık doğrudan başlamaz: önce `/api/ai/pro/propose` ile ne uygulanacağını hesaplar,
 * bu modal hekime GÖSTERİR, hekim onaylarsa `/api/ai/pro/start` onay kimliğiyle çağrılır.
 * Onay tek kullanımlık + süreli; uygulanacak parametreler backend'de MÜHÜRLÜdür (istemci
 * onaydan sonra başka değer gönderemez — bkz. servers/ai_approval.py).
 *
 * TASARIM:
 *  * "Onayla" birincil ama otomatik-odaklı DEĞİL — kazara Enter'la otonom tedavi başlamasın.
 *  * "Reddet" GEREKÇE ister: hem denetim izi hem model iyileştirmesi için gerçek veri.
 *  * Kapatma (X / dışa tıklama) = REDDETME DEĞİL, sadece ertelemedir; öneri açık kalır ve
 *    süresi dolunca kendiliğinden geçersizleşir. Sessizce "reddedildi" saymak yanıltıcı olurdu.
 *  * Duty'ler yüzde olarak gösterilir (model 0-1 üretir) — hekim klinik birimde okur.
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { ScrollableModalCard } from "@/components/ui/ScrollableModalCard";
import { IconButton } from "@/components/ui/IconButton";
import { CheckCircle2, X, XCircle } from "lucide-react-native";

import { colors, radius, rf, rs, spacing, touch } from "@/theme/tokens";
import { modelProfili } from "@/components/domain/aiProProfilleri";
import { KalibrasyonRozeti } from "@/components/domain/aipro/KalibrasyonRozeti";
import { OdakOzeti, type OdakOzet } from "@/components/domain/aipro/OdakOzeti";
import { Trans, useTranslation } from "react-i18next";
import i18n from "i18next";

export interface AiProposalSpecs {
  organ_id: number;
  duration_minutes: number;
  coil_ids: number[];
  /** Bobin başına duty (0-1) */
  D: number[];
  /** Bobin başına faz (derece) */
  P: number[];
  e_field: number;
  // ── Araştırma hattı (Faz 2/3) MÜHÜRLÜ yalnız-ek alanları; kedi önerisinde yok/boş ──
  /** MÜHÜRLENEN hedef modeli ("kedi" | "fantom" | "petri"). `/start` modeli BURADAN okur. */
  model?: string;
  /** Seçili hedefin adı ("Tümör 1", "Kuyu 3 · Kanserli"). */
  target_label?: string;
  /** Hedefin (kanserli sınıf) göreli alan öngörüsü — birimsiz. */
  e_cancer?: number | null;
  /** Çevrenin (sağlıklı sınıf) göreli alan öngörüsü — seçiciliği gösterir. */
  e_healthy?: number | null;
  /** D2.E15: MÜHÜRLENEN hasta (opak kimlik + ad) — `/start` seansı buna bağlar. Boş = hasta seçilmedi (sahipsiz). */
  patient_id?: string;
  patient_name?: string;
  /** T3 · Y189: KOŞULSUZ öneri (engeller atlandı) — mühürde; `/start` seansı bu kipte açar. Alan yoksa koşullu. */
  kosulsuz?: boolean;
  /** ODAK (istem 45): faz / duty'yi üreten planın fizik denetimi (doz, tavan, çevre, oran, konum payı, petride 24 kuyu). */
  odak?: OdakOzet;
}

export interface AiProposalMeta {
  x_mm?: number;
  y_mm?: number;
  z_mm?: number;
  reliability?: number;
  /** 3B konum yöntemi — "aruco_pnp" = kabin işaretiyle ölçüldü (karar #4: zorunlu). */
  method?: string;
  /** Konum modelin eğitim örnekleminin DIŞINDA mı — sürüşü engellemez, UYARIR. */
  ood?: boolean;
  /** Y143: araştırmada "otomatik" hedef SEÇİLİ hedefin kimliğiyle mühürlendi (seans boyunca yalnız o sürülür). */
  otomatik_secim?: boolean;
  /** Kadrajda aranan özne ("hayvan" | "fantom" | "petri plakası"). */
  subject_label?: string;
  /** Sunum-katmanı XAI (2026-08-26): "önerilen dozu en çok ne belirledi" — backend
   *  hafif D-kanal duyarlılığı (|Δ| azalan). Alan yoksa (eski backend / XAI zarif
   *  düşüşü) satır gizlenir. AI1.X6 (hoca XAI v3): yalnız etkisi > 0 olan ÖĞRENİLMİŞ girdiler "belirleyen"dir;
   *  `ogrenilmemis` (eğitimde sabit — açıklamaya katılmaz) ve `egitim_disi` (değer eğitim aralığı dışında —
   *  açıklama ekstrapolasyon) ayrı satırlarda gösterilir. */
  xaiSensitivity?: XaiDuyarlilik[];
}

/** Canlı EM duyarlılık öğesi (backend `em_runtime.hizli_sensitivity`). */
export type XaiDuyarlilik = {
  feature: string;
  etki: number | null;
  egitim_disi?: boolean;
  ogrenilmemis?: boolean;
  surukleyen?: boolean;
};

/** AI1.X6: "dozu belirleyen" = öğrenilmiş + belirleyen işaretli öğeler (eski backend'in düz listesi de buraya düşer). */
export function xaiSatirlari(liste: XaiDuyarlilik[] | undefined, etiket: Record<string, string>) {
  const ad = (f: string) => etiket[f] ?? f;
  const l = Array.isArray(liste) ? liste : [];
  return {
    belirleyen: l.filter((t) => !t.ogrenilmemis && t.surukleyen !== false)
      .map((t) => ad(t.feature) + (t.egitim_disi ? i18n.t("ai.pro.xai.egitimDisiEk") : "")),
    egitimDisi: l.filter((t) => t.egitim_disi).map((t) => ad(t.feature)),
    ogrenilmemis: l.filter((t) => t.ogrenilmemis).map((t) => ad(t.feature)),
  };
}

/** EM girdi adları → hekim diline (öneri ekranı). */
const xaiEtiketleri = (arastirma: boolean): Record<string, string> => ({
  x: i18n.t("ai.pro.xai.konumX"),
  y: i18n.t("ai.pro.xai.konumY"),
  z: i18n.t("ai.pro.xai.konumZ"),
  // Araştırma hattında `organ_id` kanalı ORGAN değil DOKU SINIFIDIR (kanserli / sağlıklı).
  organ_id: arastirma ? i18n.t("ai.pro.xai.dokuTipi") : i18n.t("ai.pro.xai.organSecimi"),
  achieved_B: i18n.t("ai.pro.xai.hedefAlan"),
  duty_sum: i18n.t("ai.pro.xai.gucButcesi"),
});

/** Dile uyan ondalık ayırıcı — TR ekranda "0,13" (klinik/akademik yazım), EN "0.13"; kodda nokta. */
function tr(n: number, basamak = 2): string {
  return Number(n ?? 0).toFixed(basamak).replace(".", i18n.language === "en" ? "." : ",");
}

export function AiSpecApprovalModal({
  visible, specs, meta, organName, busy, onApprove, onReject, onDismiss, surusKapali, onYenidenHesapla, hata, hedefGosterim,
}: {
  visible: boolean;
  specs: AiProposalSpecs | null;
  meta?: AiProposalMeta | null;
  organName?: string;
  busy?: boolean;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onDismiss: () => void;
  /** Y142 (sahip 2026-10-13): doluysa bu öneriyle SÜRÜŞ BAŞLATILAMAZ — değeri NEDEN metnidir (backend `surusKapaliNedeni`).
   *  Öneri yine incelenir ve reddedilebilir; onay düğmesi pasiftir ve bunu SÖYLER (düğme etiketi gerçeği söyler). */
  surusKapali?: string;
  /** ODAK: doz / petri kipi değişince yeni öneri iste (yeni mühür). Verilmezse doz seçici gösterilmez. */
  onYenidenHesapla?: (doz: number, kip: string, kuyu?: string) => void;
  /** AP-B4: bu penceredeki isteğin (yeniden hesapla / onay / başlat) hatası — HER ZAMAN görünen alt şeritte, düğmelerin üstünde. */
  hata?: string;
  /** AP-22: hedefin İSTEK dilindeki gösterim adı (öneri yanıtı `hedefGosterim`). Boş / yoksa ham `specs.target_label` (eski backend, kedi). */
  hedefGosterim?: string;
}) {
  const { t } = useTranslation();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  /** ODD B-2: ODAK özetindeki doz / kip / kuyu seçimi bu önerinin planından farklı → onay PASİF (onaylanan = ekranda görünen). */
  const [kirli, setKirli] = useState(false);
  useEffect(() => {
    setKirli(false);
  }, [specs]);

  if (!specs) return null;

  // L1-7.16: `?? 0` geri dönüşleri KALDIRILDI (ölüydü): mühür `coil_ids` ile `D` / `P`yi HEP 7'şer, `e_field`i HEP sayı yazar
  // (ai_router `/ai/pro/propose` → `ai_approval.create`; tip `D` / `P` / `e_field` zorunlu). Eksik değer 0 diye UYDURULMAZ (Y6).
  const rows = (specs.coil_ids || []).map((cid, i) => ({
    cid,
    duty: Number(specs.D[i]),
    phase: Number(specs.P[i]),
  }));
  const surulen = rows.filter((r) => r.duty > 0).length;
  // ── ARAŞTIRMA SUNUMU: model MÜHÜRDEN okunur (istemcinin o anki seçimi DEĞİL) — onay ekranı
  //    gerçekten neyin onaylandığını göstermek zorundadır. Alan yoksa kedi (eski öneri).
  const model = String(specs.model || "kedi");
  const arastirma = model !== "kedi";
  const modelAdi = arastirma ? modelProfili(model).baslik : "";
  const hedefEtiketi = arastirma ? modelProfili(model).hedefEtiketi : t("ai.pro.profil.kedi.hedefEtiketi");
  // AP-22: gösterim adı önce — ham VERİ etiketi ("Kuyu C6") EN arayüzde Türkçe kalıyordu (D ekran görüntüsü 14-11).
  const hedefAdi = hedefGosterim || specs.target_label || organName || `#${specs.organ_id}`;
  const eHedef = Number(specs.e_cancer ?? specs.e_field);
  const eCevre = Number(specs.e_healthy ?? 0);
  const konumVar =
    typeof meta?.x_mm === "number" && typeof meta?.y_mm === "number" && typeof meta?.z_mm === "number";
  const guven = typeof meta?.reliability === "number" ? meta.reliability : null;
  // Düşük lokalizasyon güveni sessiz kalmamalı — hekim onaylarken bunu bilmeli.
  const dusukGuven = guven !== null && guven < 0.5;

  const kapat = () => { setRejecting(false); setReason(""); onDismiss(); };

  return (
    // [S5 adım 10 / ekranB-10] ONAY SATIRI ARTIK SABİT. Kart yüzde tabanlı maxHeight ile
    // kaydırılamıyordu: 8 bobinli öneride ve yatay telefonda (yükseklik 360-430) "Onayla ve Başlat"
    // kartın altında ekran DIŞINDA kalıyordu — hekim onay veremediği için seans hiç başlamıyordu.
    // Gövde kaydırılır, eylem satırı her zaman görünür. Onay/red handler'ları DEĞİŞMEDİ.
    <ScrollableModalCard
      visible={visible}
      onRequestClose={kapat}
      onBackdropPress={kapat}
      maxWidth={rs(520)}
      testID="ai-onay"
      accessibilityLabel={t("ai.pro.onay.pencereEtiketi")}
      contentStyle={s.icerik}
      header={
        <View style={s.head}>
          <View style={{ flex: 1 }}>
            <Text style={s.title} numberOfLines={2}>
              {arastirma ? t("ai.pro.onay.baslikArastirma", { modelAdi, hedefAdi }) : t("ai.pro.onay.baslik")}
            </Text>
            {/* ⚠️ DÜRÜSTLÜK: fantom/petri klinik bir teşhis değil; onaylayan kişi bunu BAŞLIKTA
                görmeli (küçük bir dipnot yeterli olmazdı). */}
            {arastirma ? <Text style={s.altBaslik}>{t("ai.pro.onay.altBaslik")}</Text> : null}
          </View>
          <IconButton label={t("ortak.kapat")} onPress={kapat}>
            <X size={rs(20)} color={colors.textMuted} />
          </IconButton>
        </View>
      }
      footer={
        <View>
        {hata ? (
          <Text testID="ai-onay-hata" style={s.hata} accessibilityRole="alert" accessibilityLiveRegion="polite">
            {`⚠️ ${hata}`}
          </Text>
        ) : null}
        {kirli && !surusKapali ? (
          <Text testID="ai-onay-kirli" style={s.hata}>{t("ai.pro.onay.kirliOnayPasif")}</Text>
        ) : null}
        {rejecting ? (
          <View style={s.rejectBox}>
            <Text style={s.rejectLabel}>{t("ai.pro.onay.redGerekcesiKayit")}</Text>
            <TextInput
              style={s.input}
              value={reason}
              onChangeText={setReason}
              placeholder={t("ai.pro.onay.redOrnek")}
              placeholderTextColor={colors.textSubtle}
              multiline
              accessibilityLabel={t("ai.pro.degerlendirme.redGerekcesi")}
            />
            <View style={s.actions}>
              <TouchableOpacity style={[s.btn, s.btnGhost]} onPress={() => setRejecting(false)}>
                <Text style={s.btnGhostText}>{t("ortak.vazgec")}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, s.btnDanger, (!reason.trim() || busy) && s.btnDisabled]}
                disabled={!reason.trim() || !!busy}
                onPress={() => onReject(reason.trim())}
                accessibilityRole="button"
                accessibilityLabel={t("ai.pro.onay.rediOnayla")}
              >
                <Text style={s.btnDangerText}>{t("ai.pro.onay.reddet")}</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <View style={s.actions}>
            <TouchableOpacity
              style={[s.btn, s.btnGhost]}
              onPress={() => setRejecting(true)}
              disabled={!!busy}
              accessibilityRole="button"
              accessibilityLabel={t("ai.pro.onay.oneriyiReddet")}
            >
              <XCircle size={rs(16)} color={colors.danger} />
              <Text style={s.btnGhostText}>{t("ai.pro.onay.reddet")}</Text>
            </TouchableOpacity>
            {surusKapali ? (
              // Y142: sürüş kapalıyken onay seans BAŞLATMAZ — düğme pasif ve etiketi bunu söyler (backend de 409 verir).
              <TouchableOpacity
                // Dokunma hedefi tabanı satır içinde de (cırcır kapısı `s.X` stillerini çözmüyor; `s.btn` zaten touch.min taşır).
                style={[s.btn, s.btnPrimary, s.btnDisabled, { minHeight: touch.min }]}
                disabled
                accessibilityRole="button"
                accessibilityState={{ disabled: true }}
                accessibilityLabel={t("ai.pro.onay.surusKapaliEtiket")}
              >
                <Text style={s.btnPrimaryText}>{t("ai.pro.onay.surusKapali")}</Text>
              </TouchableOpacity>
            ) : (
            <TouchableOpacity
              style={[s.btn, s.btnPrimary, (busy || kirli) && s.btnDisabled]}
              onPress={onApprove}
              disabled={!!busy || kirli}
              accessibilityRole="button"
              accessibilityState={{ disabled: !!busy || kirli }}
              accessibilityLabel={t("ai.pro.onay.onaylaEtiket")}
              testID="ai-onay-onayla"
            >
              <CheckCircle2 size={rs(16)} color="#04121F" />
              <Text style={s.btnPrimaryText}>{busy ? t("ai.pro.onay.baslatiliyor") : t("ai.pro.onay.onaylaBaslat")}</Text>
            </TouchableOpacity>
            )}
          </View>
        )}
        </View>
      }
    >
          {surusKapali ? (
            <>
              <Text style={s.surusKapali} testID="ai-onay-surus-kapali">{surusKapali}</Text>
              <Text style={s.lead}>
                <Trans i18nKey="ai.pro.onay.surusKapaliLead" components={{ kalin: <Text style={s.bold} /> }} />
              </Text>
            </>
          ) : (
          <Text style={s.lead}>
            {arastirma ? (
              <Trans i18nKey="ai.pro.onay.leadDeney" components={{ kalin: <Text style={s.bold} /> }} />
            ) : (
              <Trans i18nKey="ai.pro.onay.leadOtonom" components={{ kalin: <Text style={s.bold} /> }} />
            )}
          </Text>
          )}

          <View style={s.summary}>
            {/* D2.E15: onaylanan seansın HASTASI (mühürden) — "A için onaylat, B'ye başlat" imkânsız; hekim kimi onayladığını görür. */}
            <Meta label={arastirma ? t("hasta.sozluk.arastirma.tekilKisa") : t("hasta.sozluk.klinik.tekil")} value={specs.patient_name || t("ai.pro.onay.hastaSecilmedi")} />
            <Meta label={hedefEtiketi} value={hedefAdi} />
            <Meta label={t("kontrol.sinir.sure")} value={t("ai.pro.onay.sureDk", { duration_minutes: specs.duration_minutes })} />
            <Meta label={t("ai.pro.onay.surulenBobin")} value={`${surulen}/${rows.length}`} />
            {arastirma ? null : <Meta label={t("ai.pro.onay.eOngoru")} value={Number(specs.e_field).toFixed(4)} />}
          </View>

          {/* KONUM: araştırmada dozu belirleyen tek girdi 3B konumdur → onaylayan kişi SAYIYI görmeli
              (kedi hattında panelde zaten metrik satırı var, modal kalabalıklaşmasın). */}
          {arastirma && konumVar ? (
            <Text style={s.konum}>
              {t("ai.pro.onay.konum", { x: tr(meta!.x_mm!, 1), y: tr(meta!.y_mm!, 1), z: tr(meta!.z_mm!, 1) })}
            </Text>
          ) : null}

          {/* ODAK (istem 45): faz / duty ODAK planından → doz ± konum payı, tavan, çevre / oran, petride 24 kuyu haritası + doz seçici.
              Eski "hedefte · çevrede · oran" satırı (hoca modelinin birimsiz E'si) ODAK önerisinde GÖSTERİLMEZ. */}
          {specs.odak ? (
            <OdakOzeti odak={specs.odak} busy={busy} onYenidenHesapla={onYenidenHesapla} onKirli={setKirli} />
          ) : null}

          {/* GÖRELİ ALAN: model birimsiz bir göreli değer üretir; "V/m" yazmak uydurma olurdu.
              Çevre değeri ölçülebilir düzeydeyse (>0,01) SEÇİCİLİK oranı da gösterilir. */}
          {arastirma && !specs.odak ? (
            <Text style={s.konum}>
              {t("ai.pro.onay.alan", { hedef: tr(eHedef) }) +
                (eCevre > 0.01 ? t("ai.pro.onay.alanCevre", { cevre: tr(eCevre), oran: tr(eHedef / eCevre, 1) }) : "")}
            </Text>
          ) : null}

          {/* 3B konum rozeti: karar #4 (kabin işareti ZORUNLU) — işaretsiz öneri zaten üretilmez,
              rozet onaylayan kişiye konumun NEYE dayandığını söyler. */}
          {/* KD-3a: öneri YALNIZ lokalize karede üretilir → sabit düzlem kipinde "kabin kalibrasyonuyla ölçüldü" (tezgâhta ArUco metni çıkıyordu). */}
          {arastirma ? <KalibrasyonRozeti yontem={meta?.method} localized /> : null}

          {/* Y143: otomatik seçim onay anında MÜHÜRLENDİ — onaylanan hedef seans boyunca DEĞİŞMEZ (görülen = sürülen). */}
          {arastirma && meta?.otomatik_secim ? (
            <Text style={s.uyari} testID="ai-onay-otomatik-muhur">
              {t("ai.pro.onay.otomatikMuhur", { hedefAdi })}
            </Text>
          ) : null}

          {arastirma && meta?.ood ? (
            <Text style={s.uyari}>
              {t("ai.pro.konumEgitimDisi")}
            </Text>
          ) : null}

          {model === "petri" ? (
            <Text style={s.uyari}>{t("ai.pro.onay.petriSinirli")}</Text>
          ) : null}

          {/* T3 · Y189: koşulsuz öneri onaylanmadan ÖNCE açıkça söylenir (doğrulanmamış konumla sürüş). */}
          {specs.kosulsuz === true ? (
            <Text style={s.uyari} testID="ai-onay-kosulsuz">
              {t("ai.pro.onay.kosulsuz")}
            </Text>
          ) : null}

          {guven !== null && (
            <Text style={[s.rel, dusukGuven && s.relWarn]}>
              {t("ai.pro.onay.guven", { guven: Math.round(guven * 100) })}
              {dusukGuven ? t("ai.pro.onay.guvenDusuk") : ""}
            </Text>
          )}

          {/* Sunum-katmanı XAI (2026-08-26): hekim onaylamadan "dozu ne belirledi" görür. */}
          {(() => {
            const x = xaiSatirlari(meta?.xaiSensitivity, xaiEtiketleri(arastirma));
            return (
              <>
                {x.belirleyen.length > 0 && <Text style={s.xai}>{t("ai.pro.onay.xaiBelirleyen", { liste: x.belirleyen.join(" · ") })}</Text>}
                {x.egitimDisi.length > 0 && (
                  <Text style={s.xai}>
                    {t("ai.pro.onay.xaiEgitimDisi", { liste: x.egitimDisi.join(", ") })}
                  </Text>
                )}
                {x.ogrenilmemis.length > 0 && (
                  <Text style={s.xai}>
                    {t("ai.pro.onay.xaiOgrenilmemis", { liste: x.ogrenilmemis.join(", ") })}
                  </Text>
                )}
              </>
            );
          })()}

          {/* [S5 adım 10] İç ScrollView → View: iç içe kaydırıcı Android'de dokunuşu çalıyordu.
              Tablo artık tek kaydırıcının (kart gövdesi) parçası. */}
          {kirli ? (
            <Text testID="ai-onay-tablo-eski" style={s.uyari}>{t("ai.pro.onay.odak.eskiPlan")}</Text>
          ) : null}
          <View style={[s.tableWrap, kirli && s.eski]} testID="ai-onay-tablo">
            <View style={[s.tr, s.trHead]}>
              <Text style={[s.th, s.cCoil]}>{t("ai.pro.tablo.bobin")}</Text>
              <Text style={[s.th, s.cDuty]}>{t("kontrol.bobin.duty")}</Text>
              <Text style={[s.th, s.cPhase]}>{t("kontrol.sinir.faz")}</Text>
            </View>
            {rows.map((r) => (
              <View key={r.cid} style={s.tr}>
                <Text style={[s.td, s.cCoil]}>{r.cid}</Text>
                <Text style={[s.td, s.cDuty, r.duty > 0 ? s.on : s.off]}>
                  {t("ai.ortak.yuzde", { deger: (r.duty * 100).toFixed(1) })}
                </Text>
                <Text style={[s.td, s.cPhase]}>{r.phase.toFixed(0)}°</Text>
              </View>
            ))}
          </View>
    </ScrollableModalCard>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.metaCell}>
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={s.metaValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  // Perde/kart iskeleti ScrollableModalCard'dan gelir (mutlak maxHeight + sabit eylem satırı).
  icerik: { gap: spacing.sm, paddingBottom: spacing.sm },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { color: colors.text, fontSize: rf(17), fontWeight: "800" },
  // Araştırma başlığının alt satırı: "klinik teşhis değil" mesajı başlıktan AYRILMADAN durur.
  altBaslik: { color: colors.warning, fontSize: rf(11), fontWeight: "700", marginTop: 2 },
  konum: { color: colors.text, fontSize: rf(12), fontWeight: "700" },
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
  // Y142: sürüş kapalı bildirimi — onay satırından ÖNCE, gövdenin başında (hekim ilk bunu okur).
  surusKapali: { color: colors.warning, fontSize: rf(12), fontWeight: "800" },
  hata: { color: colors.danger, fontSize: rf(12), fontWeight: "700", marginBottom: spacing.xs },
  lead: { color: colors.textMuted, fontSize: rf(12), lineHeight: rf(18) },
  bold: { color: colors.text, fontWeight: "800" },
  summary: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  metaCell: { minWidth: rs(96), backgroundColor: colors.bgAlt, borderRadius: radius.md, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  metaLabel: { color: colors.textSubtle, fontSize: rf(10) },
  metaValue: { color: colors.text, fontSize: rf(13), fontWeight: "700" },
  rel: { color: colors.textMuted, fontSize: rf(11) },
  relWarn: { color: colors.warning, fontWeight: "700" },
  // Sunum-katmanı XAI satırı (2026-08-26)
  xai: { color: colors.textMuted, fontSize: rf(11), marginTop: 2 },
  // maxHeight kaldırıldı: tablo artık kart gövdesiyle birlikte kayıyor (iç içe kaydırıcı yok).
  tableWrap: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  eski: { opacity: 0.4 }, // ODD B-2: önceki plan (yeniden hesaplanmadı)
  tr: { flexDirection: "row", paddingVertical: rs(6), paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  trHead: { backgroundColor: colors.bgAlt },
  th: { color: colors.textSubtle, fontSize: rf(11), fontWeight: "700" },
  td: { color: colors.text, fontSize: rf(12) },
  cCoil: { width: rs(56) },
  cDuty: { flex: 1 },
  cPhase: { width: rs(64), textAlign: "right" },
  on: { color: colors.success, fontWeight: "700" },
  off: { color: colors.textSubtle },
  rejectBox: { gap: spacing.xs },
  rejectLabel: { color: colors.textMuted, fontSize: rf(11) },
  input: { minHeight: rs(64), backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, color: colors.text, padding: spacing.sm, fontSize: rf(12), textAlignVertical: "top" },
  actions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.xs },
  // [S3] Onay/red düğmeleri: 320 px'te rs(10) dolgu ile 34 px yükseklikte kalıyordu.
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: rs(6),
         minHeight: touch.min, paddingVertical: rs(10), paddingHorizontal: spacing.md, borderRadius: radius.md },
  btnPrimary: { backgroundColor: colors.cyan },
  btnPrimaryText: { color: "#04121F", fontWeight: "800", fontSize: rf(13) },
  btnDanger: { backgroundColor: colors.danger },
  btnDangerText: { color: "#fff", fontWeight: "800", fontSize: rf(13) },
  btnGhost: { borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.textMuted, fontWeight: "700", fontSize: rf(13) },
  btnDisabled: { opacity: 0.5 },
});
