// Author: mertaygn
/**
 * GENİŞLETİLEBİLİR METİN — "üç noktadan sonrası okunamıyor" (sahip bildirimi 2026-09-12).
 * =====================================================================================
 * · "bildirim sığmayınca üç noktadan sonrasını kullanıcı hiçbir şekilde okuyamıyor,
 *    bildirimin üzerine tıklayınca tamamının açılması lazım aslında."
 * · "ai analiz detaylarında yine üç nokta sorunu ve devamını göremeyiş ... bunların üzerine
 *    tıklayınca tam metni gösterme özelliği kazandırılmalı."
 *
 * ⚠️ NEDEN CİDDİ: bu ürünün bildirimleri EYLEM söyler ("…Kartı güncel firmware ile yeniden
 * programlayın"). Kesilen kısım tam da o eylem cümlesiydi — yani uyarı, ne yapılacağını
 * söyleyemeyen bir uyarıya dönüşüyordu.
 */
import { fireEvent, render } from "@testing-library/react-native";
import { GenisletilebilirMetin } from "@/components/ui/GenisletilebilirMetin";
import { SATIR_BASINA_KARAKTER, kirpikOlabilir } from "@/utils/metinKirpma";

const UZUN =
  "STM32 komutları REDDEDİYOR (CRC) — karttaki firmware sürümü bu uygulamayla uyuşmuyor. " +
  "Hiçbir bobin çalışmaz. Kartı güncel firmware ile yeniden programlayın.";

// ============================================================================
// 1. ⚠️ ASIL KAPI — DOKUNUNCA TAM METİN AÇILIR
// ============================================================================

test("KRITIK: kapaliyken KIRPILIR, dokununca TAMAMI acilir", () => {
  // MUTASYON: `numberOfLines={acik ? undefined : satir}` yerine sabit `satir` yaz → KIRMIZI
  // (dokunuş bir şey değiştirmez; sahibin bildirdiği arıza aynen sürer).
  const api = render(
    <GenisletilebilirMetin satir={1} testID="t">
      {UZUN}
    </GenisletilebilirMetin>,
  );
  const metin = api.getByTestId("t-metin");
  expect(metin.props.numberOfLines).toBe(1);

  fireEvent.press(api.getByTestId("t"));
  expect(api.getByTestId("t-metin").props.numberOfLines).toBeUndefined();
});

test("KRITIK: tekrar dokununca KAPANIR (tek yonlu degil)", () => {
  const api = render(
    <GenisletilebilirMetin satir={2} testID="t">
      {UZUN}
    </GenisletilebilirMetin>,
  );
  fireEvent.press(api.getByTestId("t"));
  fireEvent.press(api.getByTestId("t"));
  expect(api.getByTestId("t-metin").props.numberOfLines).toBe(2);
});

test("KRITIK: YETENEK sezgiye BAGLI DEGIL — ipucu yokken de dokunus acar", () => {
  // ⚠️ BU KAPININ ASIL DERSİ: kırpılma sezgisi yanılabilir (platforma göre satıra sığan
  // karakter sayısı değişir). Sezgi "kırpılmadı" dese bile metne ULAŞILABİLMELİ; aksi halde
  // sezginin yanıldığı her durumda arıza geri gelirdi.
  //
  // MUTASYON: `TouchableOpacity`yi `disabled={!ipucuGoster}` yap → KIRMIZI.
  const api = render(
    <GenisletilebilirMetin satir={3} testID="t">
      kısa
    </GenisletilebilirMetin>,
  );
  expect(api.queryByTestId("t-ipucu")).toBeNull(); // ipucu YOK (dogru)
  fireEvent.press(api.getByTestId("t"));
  expect(api.getByTestId("t-metin").props.numberOfLines).toBeUndefined(); // ama YETENEK VAR
});

// ============================================================================
// 2. İPUCU — KULLANICI GİZLİ BİR ÖZELLİK ARAMASIN
// ============================================================================

test("KRITIK: kirpilmis metinde 'Tumunu gor' IPUCU gorunur", () => {
  // ⚠️ İpucu olmadan bu özellik GİZLİ kalırdı: kullanıcı metnin dokunulabilir olduğunu
  // bilemez ve üç noktanın arkasını yine okuyamaz — düzeltme yapılmamış sayılır.
  //
  // MUTASYON: `ipucuGoster`i `false` yap → KIRMIZI.
  const api = render(
    <GenisletilebilirMetin satir={1} testID="t">
      {UZUN}
    </GenisletilebilirMetin>,
  );
  expect(api.getByTestId("t-ipucu").props.children).toContain("Tümünü gör");
  fireEvent.press(api.getByTestId("t"));
  expect(api.getByTestId("t-ipucu").props.children).toContain("Daha az");
});

test("KRITIK: EKRAN OKUYUCU genisleme durumunu bildirir", () => {
  const api = render(
    <GenisletilebilirMetin satir={1} testID="t">
      {UZUN}
    </GenisletilebilirMetin>,
  );
  const dugme = api.getByTestId("t");
  expect(dugme.props.accessibilityRole).toBe("button");
  expect(dugme.props.accessibilityState.expanded).toBe(false);
  fireEvent.press(dugme);
  expect(api.getByTestId("t").props.accessibilityState.expanded).toBe(true);
});

test("metin SECILEBILIR kalir (kopyalama kaybolmasin)", () => {
  const api = render(
    <GenisletilebilirMetin satir={2} testID="t">
      {UZUN}
    </GenisletilebilirMetin>,
  );
  expect(api.getByTestId("t-metin").props.selectable).toBe(true);
});

// ============================================================================
// 3. KIRPILMA SEZGİSİ (saf fonksiyon)
// ============================================================================

test("KRITIK: sezgi KACIRMAKTANSA fazladan ipucu gosterir", () => {
  // ⚠️ Yön önemli: kırpılmış metinde ipucu göstermemek arızayı sürdürür; kırpılmamışta
  // göstermek yalnız kozmetiktir. Eşik bu yüzden dar sütuna göre DÜŞÜK tutulur.
  expect(kirpikOlabilir("x".repeat(SATIR_BASINA_KARAKTER * 2 + 1), 2)).toBe(true);
  expect(kirpikOlabilir("kısa", 2)).toBe(false);
});

test("KRITIK: ACIK satir sonlari da kirpilma sayilir", () => {
  // Üç kısa satır, `satir=2` ile kesilir ama karakter eşiğinin ALTINDADIR — yalnız uzunluğa
  // bakan bir sezgi bunu kaçırırdı.
  //
  // MUTASYON: `s.split("\n").length > satir` kontrolünü kaldır → KIRMIZI.
  expect(kirpikOlabilir("a\nb\nc", 2)).toBe(true);
  expect(kirpikOlabilir("a\nb", 2)).toBe(false);
});

test("bos/gecersiz girdide ipucu YOK (cokmez)", () => {
  expect(kirpikOlabilir("", 2)).toBe(false);
  expect(kirpikOlabilir(null, 2)).toBe(false);
  expect(kirpikOlabilir(undefined, 2)).toBe(false);
  expect(kirpikOlabilir("uzun".repeat(50), 0)).toBe(false);
});
