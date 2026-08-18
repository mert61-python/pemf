/**
 * Saha hatası (2026-08-15, laptop/web): ses kaydedip "Analiz Et" deyince
 *   "The method or property expo-file-system.readAsStringAsync is not available on web"
 *
 * Web'de İKİ yol vardı ve yalnız biri `webFile` üretiyordu: dosya seçme gerçek bir `File`
 * veriyor, CANLI KAYIT ise sadece `blob:` URI bırakıyordu. Yükleme dalı
 * `Platform.OS === 'web' && webFile` diye seçildiği için kayıt yolu NATIVE dalına düşüyor
 * ve web'de var olmayan `expo-file-system`i çağırıyordu.
 *
 * Bu testlerin asıl işi: web'de native okuyucunun ASLA çağrılmadığını kanıtlamak.
 */
import { sesFormDataHazirla, uriyiDosyayaCevir, VARSAYILAN_SES_ADI } from "../sesYukleme";

const gercekFetch = global.fetch;

function blobDondur(icerik: string, tip = "audio/mp4", ok = true, status = 200) {
  global.fetch = jest.fn().mockResolvedValue({
    ok,
    status,
    blob: async () => new Blob([icerik], { type: tip }),
  }) as any;
}

afterEach(() => {
  global.fetch = gercekFetch;
  jest.restoreAllMocks();
});

describe("web", () => {
  it("KRİTİK: canlı kayıtta (webFile YOK, blob: URI VAR) native okuyucu ÇAĞRILMAZ", async () => {
    blobDondur("sesverisi");
    const nativeOku = jest.fn(async () => "base64");

    const form = await sesFormDataHazirla(
      { webFile: null, uri: "blob:http://localhost/abc-123", fileName: "kayıt.m4a" },
      true,
      nativeOku,
    );

    expect(nativeOku).not.toHaveBeenCalled(); // ← saha hatası tam olarak buydu
    expect(form.get("file")).toBeInstanceOf(File);
    expect(form.get("audio_base64")).toBeNull();
    expect((form.get("file") as File).name).toBe("kayıt.m4a");
  });

  it("seçilen dosya varsa onu kullanır, fetch'e hiç gitmez", async () => {
    global.fetch = jest.fn() as any;
    const nativeOku = jest.fn(async () => "base64");
    const secilen = new File(["x"], "secilen.mp3", { type: "audio/mpeg" });

    const form = await sesFormDataHazirla(
      { webFile: secilen, uri: "web", fileName: "secilen.mp3" },
      true,
      nativeOku,
    );

    expect(global.fetch).not.toHaveBeenCalled();
    expect(nativeOku).not.toHaveBeenCalled();
    // NOT: kimlik (`toBe`) karşılaştırılamaz — `FormData.append(ad, dosya, dosyaAdi)` üçüncü
    // argüman verilince File'ı YENİDEN SARMALAR. Anlamlı olan içerik/ad/tip.
    const gonderilen = form.get("file") as File;
    expect(gonderilen.name).toBe("secilen.mp3");
    expect(gonderilen.type).toBe("audio/mpeg");
    expect(await gonderilen.text()).toBe("x");
  });

  it("nöbetçi 'web' URI'si tek başına analiz edilebilir sayılmaz", async () => {
    // pickAudio web dalı iptal edilirse audioUri "web" kalabilir; bu gerçek bir kaynak DEĞİL.
    await expect(
      sesFormDataHazirla({ webFile: null, uri: "web" }, true, async () => "base64"),
    ).rejects.toThrow(/ses yok/i);
  });

  it("boş kayıt (0 bayt blob) sunucuya gönderilmez — anlaşılır hata verir", async () => {
    blobDondur("");
    await expect(
      sesFormDataHazirla({ webFile: null, uri: "blob:bos" }, true, async () => "base64"),
    ).rejects.toThrow(/boş/i);
  });

  it("kayıt okunamazsa (HTTP hatası) anlaşılır hata verir", async () => {
    blobDondur("x", "audio/mp4", false, 404);
    await expect(
      sesFormDataHazirla({ webFile: null, uri: "blob:yok" }, true, async () => "base64"),
    ).rejects.toThrow(/okunamadı/i);
  });

  it("dosya adı verilmezse varsayılana düşer", async () => {
    blobDondur("ses");
    const form = await sesFormDataHazirla({ webFile: null, uri: "blob:x" }, true, async () => "b");
    expect((form.get("file") as File).name).toBe(VARSAYILAN_SES_ADI);
  });

  it("blob MIME'ı boşsa makul bir varsayılan atanır (bazı tarayıcılar kaybediyor)", async () => {
    blobDondur("ses", "");
    const dosya = await uriyiDosyayaCevir("blob:x", "kayit.m4a");
    expect(dosya.type).toBe("audio/mp4");
  });
});

describe("native", () => {
  it("base64 okur ve audio_base64 alanına koyar (multipart file:// okuyamıyor)", async () => {
    const nativeOku = jest.fn(async () => "QUJD");
    global.fetch = jest.fn() as any;

    const form = await sesFormDataHazirla(
      { webFile: null, uri: "file:///data/kayit.m4a", fileName: "kayıt.m4a" },
      false,
      nativeOku,
    );

    expect(nativeOku).toHaveBeenCalledWith("file:///data/kayit.m4a");
    expect(form.get("audio_base64")).toBe("QUJD");
    expect(form.get("file")).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled(); // native'de blob çevrimi YOK
  });

  it("URI yoksa hata verir", async () => {
    await expect(
      sesFormDataHazirla({ webFile: null, uri: null }, false, async () => "b"),
    ).rejects.toThrow(/ses yok/i);
  });

  it("native'de webFile varsa bile YOK SAYILIR (platform kararı veriyi ezer)", async () => {
    // Kullanıcı web'de seçip sonra native'e geçemez; ama durum sızarsa native yolu
    // base64 okumaya devam etmeli — sunucu native'den `file` alanı beklemiyor.
    const nativeOku = jest.fn(async () => "QUJD");
    const form = await sesFormDataHazirla(
      { webFile: new File(["x"], "a.mp3"), uri: "file:///a.m4a" },
      false,
      nativeOku,
    );
    expect(form.get("audio_base64")).toBe("QUJD");
    expect(form.get("file")).toBeNull();
  });
});
