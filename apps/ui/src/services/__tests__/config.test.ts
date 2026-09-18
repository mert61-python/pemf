// Author: mertaygn, cglrgrkn
/**
 * config kritik davranışları (audit B-3.2): sunucu adresi → API/WS URL çözümü (LAN IP vs
 * Cloudflare tünel) + API token kalıcılığı (AsyncStorage). Bağlantının belkemiği.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as config from "@/services/config";

beforeEach(async () => {
  await AsyncStorage.clear();
  config.serviceConfig.apiToken = "";
});

describe("updateServiceConfig — URL çözümü", () => {
  it("düz IP → http + :8000 + /api ve ws://", () => {
    config.updateServiceConfig("192.168.1.147");
    expect(config.serviceConfig.apiBaseUrl).toBe("http://192.168.1.147:8000/api");
    expect(config.serviceConfig.websocketUrl).toBe("ws://192.168.1.147:8000/ws");
  });

  it("https tünel → wss + /api (port eklenmez)", () => {
    config.updateServiceConfig("https://abcd-xyz.trycloudflare.com");
    expect(config.serviceConfig.apiBaseUrl).toBe("https://abcd-xyz.trycloudflare.com/api");
    expect(config.serviceConfig.websocketUrl).toBe("wss://abcd-xyz.trycloudflare.com/ws");
  });

  it("sondaki '/' kaldırılır", () => {
    config.updateServiceConfig("http://10.0.0.5:8000/");
    expect(config.serviceConfig.apiBaseUrl).toBe("http://10.0.0.5:8000/api");
  });

  it("mevcut apiToken korunur (ağ değişince kullanıcı yeniden uğraşmaz)", () => {
    config.serviceConfig.apiToken = "keep-me";
    config.updateServiceConfig("192.168.1.1");
    expect(config.serviceConfig.apiToken).toBe("keep-me");
  });

  // #63 path-injection düzeltmesi TESTSİZDİ → sessizce geri gelebilirdi.
  it("KRİTİK: geçersiz adres REDDEDİLİR (false) ve mevcut ayarı BOZMAZ", () => {
    config.updateServiceConfig("192.168.1.147");
    const before = { ...config.serviceConfig };
    for (const bad of ["192.168.1.1/evil", "", "   ", "10.0.0.1 evil", "host\\path", "a<b>c"]) {
      expect(config.updateServiceConfig(bad)).toBe(false);
      expect(config.serviceConfig.apiBaseUrl).toBe(before.apiBaseUrl);
      expect(config.serviceConfig.websocketUrl).toBe(before.websocketUrl);
    }
  });

  it("geçerli adres true döner", () => {
    expect(config.updateServiceConfig("192.168.1.40")).toBe(true);
    expect(config.updateServiceConfig("https://x-y.trycloudflare.com")).toBe(true);
  });
});

describe("API token kalıcılığı", () => {
  it("setStoredApiToken saklar + loadStoredApiToken geri yükler", async () => {
    await config.setStoredApiToken("abc123");
    expect(config.serviceConfig.apiToken).toBe("abc123");

    config.serviceConfig.apiToken = ""; // belleği sıfırla, diskten yükle
    await config.loadStoredApiToken();
    expect(config.serviceConfig.apiToken).toBe("abc123");
  });

  it("boş token → depodan silinir; loadStoredApiToken mevcut değeri EZMEZ", async () => {
    await config.setStoredApiToken("x");
    await config.setStoredApiToken("");
    expect(config.serviceConfig.apiToken).toBe("");

    config.serviceConfig.apiToken = "in-memory";
    await config.loadStoredApiToken(); // depo boş → değişmemeli
    expect(config.serviceConfig.apiToken).toBe("in-memory");
  });
});

describe("cihaz kimliği + otomatik-eşleştirme bayrağı", () => {
  it("setStoredDeviceId saklar ve getStoredDeviceId geri verir", async () => {
    await config.setStoredDeviceId("PEMF-001");
    expect(await config.getStoredDeviceId()).toBe("PEMF-001");
  });

  it("device_id DEĞİŞİNCE just_paired bayrağı yazılır", async () => {
    await config.setStoredDeviceId("PEMF-001");
    await config.setStoredDeviceId("PEMF-002"); // değişti
    expect(await AsyncStorage.getItem("@pemf_just_paired")).toBe("PEMF-002");
  });

  it("boş id yok sayılır", async () => {
    await config.setStoredDeviceId("");
    expect(await config.getStoredDeviceId()).toBeNull();
  });
});
