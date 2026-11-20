// Author: mertaygn, cglrgrkn
/**
 * Y308 (sahip 19-11) — KABİN SENSÖRÜ (MLX) KONUMU, İSTEĞE BAĞLI: seans sırasında (`/session/sensor_konumu`, sunucu saati) ya da seans
 * bittikten sonra (`/history/{id}/sensor_konumu`, başlangıç saati seçilerek). Hata metni sunucudan (eylem söyler, TR + EN) çağırana
 * verilir; ACİL DURDUR / sürüş bu çağrılara hiçbir koşulla bağlı DEĞİLDİR.
 */
import { apiDelete, apiGet, apiPost } from "@/services/apiClient";

export type SensorKonumuGovde = {
  serbest: boolean;
  solCm?: number;
  onCm?: number;
  yukseklikCm?: number;
  notMetni?: string;
  zamanEpoch?: number;
};

export type SensorKonumuKaydi = {
  id: number;
  session_id?: number;
  zaman_epoch: number;
  serbest: boolean;
  sol_cm: number | null;
  on_cm: number | null;
  yukseklik_cm: number | null;
  not_metni: string;
};

export type KonumDilimi = {
  baslangic_epoch: number;
  bitis_epoch: number;
  sure_sn: number;
  serbest: boolean;
  kayit_id: number | null;
  sol_cm: number | null;
  on_cm: number | null;
  yukseklik_cm: number | null;
  not: string;
  olcum_sayisi: number;
  ortalama_mt: number | null;
  tepe_mt: number | null;
  tahmin_mt: number | null;
  fark_yuzde: number | null;
};

type Hata = (mesaj: string) => void;
const hataSecenekleri = (hata: Hata) => ({
  silent: true,
  onHttpError: (durum: number, detay?: string) => hata(detay || String(durum)),
});

/** Aktif seansın son konum girişi; seans yoksa `aktif: false`. Bağlantı yoksa null. */
export function canliKonum(): Promise<{ aktif: boolean; konum: SensorKonumuKaydi | null } | null> {
  return apiGet("/session/sensor_konumu", null, { silent: true });
}

/** Aktif seansa giriş (şimdiki zaman). Başarı → true; hata metni `hata`ya. */
export async function canliKonumEkle(govde: SensorKonumuGovde, hata: Hata): Promise<boolean> {
  return (await apiPost<{ status: string } | null>("/session/sensor_konumu", govde, null, hataSecenekleri(hata))) !== null;
}

/** Seans sonrası giriş (zamanEpoch seans aralığında). */
export async function gecmisKonumEkle(seansId: number | string, govde: SensorKonumuGovde, hata: Hata): Promise<boolean> {
  return (await apiPost<{ status: string } | null>(`/history/${seansId}/sensor_konumu`, govde, null, hataSecenekleri(hata))) !== null;
}

/** Seans sonrası giriş silme. */
export async function gecmisKonumSil(seansId: number | string, kayitId: number): Promise<boolean> {
  return (await apiDelete<{ status: string } | null>(`/history/${seansId}/sensor_konumu/${kayitId}`, null)) !== null;
}
