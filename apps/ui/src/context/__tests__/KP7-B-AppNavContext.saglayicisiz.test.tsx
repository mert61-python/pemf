/**
 * KP-7 B (madde 7 · işlev ölçüsü): `AppNavContext` VARSAYILAN değeri — sağlayıcı olmadan çizilen tüketici (tek başına çizilen
 * ekran / bileşen testi) gezinme / hasta / AI Pro modeli yazıcılarını çağırdığında SESSİZCE yok sayılır: fırlatmaz, değer değişmez,
 * Kontrol belleği YOK. (Önceden bu üç yazıcı hiçbir testte çağrılmıyordu.)
 */
import { act, renderHook } from "@testing-library/react-native";
import { useAppNav } from "@/context/AppNavContext";

describe("KP-7 B · AppNavContext sağlayıcısız varsayılan", () => {
  test("yazıcılar no-op: fırlatmaz, seçili hasta / model / bellek değişmez", () => {
    const h = renderHook(() => useAppNav());
    expect(h.result.current.selectedPatient).toBeNull();
    expect(h.result.current.aiProModeli).toBe("");
    expect(h.result.current.kontrolHafizasi).toBeUndefined();
    act(() => {
      expect(() => h.result.current.navigateTo("control" as never)).not.toThrow();
      expect(() => h.result.current.setSelectedPatient({ id: "p1", name: "Pamuk" } as never)).not.toThrow();
      expect(() => h.result.current.setAiProModeli("model-x")).not.toThrow();
    });
    h.rerender({});
    expect(h.result.current.selectedPatient).toBeNull();
    expect(h.result.current.aiProModeli).toBe("");
  });
});
