/**
 * KP-7 B (madde 7 · işlev ölçüsü): `LiveDataContext` VARSAYILAN değeri — sağlayıcı olmadan çizilen tüketici (tek başına çizilen ekran /
 * bileşen testi) okundu işaretleme / bildirim temizleme / yenileme / yeniden bağlanma çağrılarını SESSİZCE yok sayar: fırlatmaz, bağlantı
 * "çevrimdışı" ve "gerçek veri yok" kalır (sahte veri canlı sanılmaz). (Önceden bu dört yazıcı hiçbir testte çağrılmıyordu.)
 */
import { act, renderHook } from "@testing-library/react-native";
import { useLiveData } from "@/context/LiveDataContext";

describe("KP-7 B · LiveDataContext sağlayıcısız varsayılan", () => {
  test("yazıcılar no-op: fırlatmaz; bağlantı çevrimdışı, gerçek veri yok, okunmamış 0 kalır", async () => {
    const h = renderHook(() => useLiveData());
    expect(h.result.current.connectionQuality).toBe("offline");
    expect(h.result.current.haveRealData).toBe(false);
    expect(h.result.current.wsConnected).toBe(false);
    await act(async () => {
      expect(() => h.result.current.markAllRead()).not.toThrow();
      expect(() => h.result.current.clearNotifications()).not.toThrow();
      await expect(h.result.current.refresh()).resolves.toBeUndefined();
      expect(() => h.result.current.reconnect()).not.toThrow();
    });
    expect(h.result.current.unreadCount).toBe(0);
    expect(h.result.current.connectionQuality).toBe("offline");
    expect(h.result.current.haveRealData).toBe(false);
  });
});
