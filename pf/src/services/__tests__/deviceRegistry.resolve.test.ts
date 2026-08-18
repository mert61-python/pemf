// Author: mertaygn, cglrgrkn
/**
 * UZAK CİHAZ ÇÖZÜMLEMESİ — "kayıt yok" ile "adres yok" AYRI SEBEPLERDİR.
 *
 * SAHA BİLDİRİMİ 2026-08-12: kullanıcı cihaz ekranındaki eşleştirme kodunu (MVPDDN) hücresel
 * veriden girdi ve **"Bu kod/kimlikle eşleşen kayıtlı cihaz bulunamadı. Kodu kontrol edin."**
 * gördü. Kodu defalarca kontrol etti — oysa kod DOĞRUYDU: cihazın `/api/health` çıktısı
 * `pairingCode: MVPDDN`, `cloudRegistry: ok` diyordu. Tek eksik `tunnel_url: None` idi
 * (cihazda uzaktan erişim açık değil; `PEMF_ENABLE_TUNNEL` varsayılan kapalı).
 *
 * KÖK KUSUR: çözümleme "satır yok" ile "satır var ama adres yok"u aynı `null`a indiriyordu.
 * Kullanıcı yanlış yere bakmaya yönlendiriliyor, gerçek sebep (cihazda ayar) gizleniyordu.
 * Bir hata mesajı NE OLDUĞUNU değil NE YAPILACAĞINI söylemelidir.
 *
 * Bu testler dört sebebin de ayrı ayrı üretildiğini kilitler.
 */
// ⚠️ `mock` ÖNEKİ ZORUNLU: jest.mock fabrikası hoist edilir ve kapsam-dışı değişkene
// erişemez; yalnız `mock*` adlarına izin verilir (ilk yazımda `rpc` dedim, süit hiç koşmadı).
const mockRpc = jest.fn();
jest.mock("@supabase/supabase-js", () => ({
  createClient: () => ({ rpc: mockRpc }), // alan adı `rpc` OLMALI — kod `c.rpc()` çağırır
}));

import {
  getRemoteUrlForDevice,
  uzakCihaziKimlikleCoz,
  uzakCihaziKodlaCoz,
} from "@/services/deviceRegistry";

const TAZE = () => new Date().toISOString();
const BAYAT = () => new Date(Date.now() - 60 * 60 * 1000).toISOString(); // 1 saat önce

function satir(over: Record<string, unknown> = {}) {
  return {
    device_id: "140936350360443",
    name: "PEMF-Vet",
    tunnel_url: "https://ornek.trycloudflare.com",
    local_ip: "192.168.1.147",
    last_seen: TAZE(),
    ...over,
  };
}

beforeEach(() => mockRpc.mockReset());

describe("uzak cihaz çözümlemesi", () => {
  it("KRITIK: cihaz kayıtlı ama tunnel_url YOK → 'adres_yok' (kod yanlış DEĞİL)", async () => {
    mockRpc.mockResolvedValue({ data: [satir({ tunnel_url: null })], error: null });
    const c = await uzakCihaziKodlaCoz("MVPDDN");
    // ⚠️ ASIL ARIZA: eskiden burası `null` dönüyor ve ekran "Kodu kontrol edin" diyordu.
    expect(c.durum).toBe("adres_yok");
    if (c.durum === "adres_yok") expect(c.device.device_id).toBe("140936350360443");
  });

  it("hiç satır yoksa → 'yok' (gerçekten yanlış kod)", async () => {
    mockRpc.mockResolvedValue({ data: [], error: null });
    expect((await uzakCihaziKodlaCoz("YANLIS")).durum).toBe("yok");
  });

  it("adres var ama heartbeat eski → 'bayat' (cihaz çevrimdışı)", async () => {
    mockRpc.mockResolvedValue({ data: [satir({ last_seen: BAYAT() })], error: null });
    expect((await uzakCihaziKodlaCoz("MVPDDN")).durum).toBe("bayat");
  });

  it("RPC hatası/zaman aşımı → 'hata' (kod yanlış DEĞİL)", async () => {
    mockRpc.mockResolvedValue({ data: null, error: { message: "boom" } });
    expect((await uzakCihaziKodlaCoz("MVPDDN")).durum).toBe("hata");

    mockRpc.mockRejectedValue(new Error("supabase timeout"));
    expect((await uzakCihaziKodlaCoz("MVPDDN")).durum).toBe("hata");
  });

  it("her şey yerindeyse → 'bulundu' + url NON-NULL", async () => {
    mockRpc.mockResolvedValue({ data: [satir()], error: null });
    const c = await uzakCihaziKodlaCoz("mvpddn"); // büyük/küçük harf duyarsız (RPC tarafında)
    expect(c.durum).toBe("bulundu");
    if (c.durum === "bulundu") expect(c.url).toBe("https://ornek.trycloudflare.com");
  });

  it("kod ve kimlik AYRI parametre ile sorulur", async () => {
    mockRpc.mockResolvedValue({ data: [satir()], error: null });
    await uzakCihaziKodlaCoz("MVPDDN");
    expect(mockRpc).toHaveBeenLastCalledWith("resolve_device", { p_code: "MVPDDN" });
    await uzakCihaziKimlikleCoz("140936350360443");
    expect(mockRpc).toHaveBeenLastCalledWith("resolve_device", { p_device_id: "140936350360443" });
  });

  it("keşif merdiveni AYNI yolu kullanır (ayrışma olmasın)", async () => {
    // getRemoteUrlForDevice kendi RPC'sini yazmamalı; `_cozumle`ye devretmeli.
    mockRpc.mockResolvedValue({ data: [satir({ tunnel_url: null })], error: null });
    expect(await getRemoteUrlForDevice("140936350360443")).toBeNull(); // adres yoksa null
    mockRpc.mockResolvedValue({ data: [satir()], error: null });
    expect(await getRemoteUrlForDevice("140936350360443")).toBe("https://ornek.trycloudflare.com");
  });
});
