/**
 * useForegroundReconnect (audit B-3.2): uygulama ön plana (active) gelince onReconnect tetiklenmeli
 * (arka planda donmuş WS'i tazele); background/inactive'de tetiklenmemeli; unmount'ta abonelik kalkmalı.
 */
import { AppState, AppStateStatus } from "react-native";
import { renderHook } from "@testing-library/react-native";
import { useForegroundReconnect } from "@/hooks/useForegroundReconnect";

it("ön plana (active) gelince onReconnect çağırır; background'da çağırmaz", () => {
  const remove = jest.fn();
  const addSpy = jest.spyOn(AppState, "addEventListener").mockReturnValue({ remove } as never);

  const onReconnect = jest.fn();
  const { unmount } = renderHook(() => useForegroundReconnect(onReconnect));

  const listener = addSpy.mock.calls[0][1];  // hook'un kaydettiği (state) => void

  listener("background" as AppStateStatus);
  expect(onReconnect).not.toHaveBeenCalled();

  listener("active" as AppStateStatus);
  expect(onReconnect).toHaveBeenCalledTimes(1);

  unmount();
  expect(remove).toHaveBeenCalled();  // abonelik temizlendi
});
