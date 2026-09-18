// Author: mertaygn, cglrgrkn
/**
 * useNetworkReachability (audit B-2.4): LiveDataContext'ten çıkarılan ağ-tespit hook'u.
 * NetInfo mock'lanır; ağ yeniden bağlanınca DEBOUNCE'lu (1.5sn) onReconnect tetiklenmeli,
 * flapping'de fırtına olmamalı, aynı durum tekrarında tetiklenmemeli.
 */
const mockAddEventListener = jest.fn<() => void, [(state: unknown) => void]>();
jest.mock("@react-native-community/netinfo", () => ({
  default: { addEventListener: mockAddEventListener },
}));

import { renderHook } from "@testing-library/react-native";
import { useNetworkReachability } from "@/hooks/useNetworkReachability";

function lastListener(): (state: { isConnected: boolean }) => void {
  return mockAddEventListener.mock.calls[mockAddEventListener.mock.calls.length - 1][0] as never;
}

beforeEach(() => {
  jest.useFakeTimers();
  mockAddEventListener.mockReset();
  mockAddEventListener.mockReturnValue(() => {});
});
afterEach(() => {
  jest.useRealTimers();
});

it("ağ bağlanınca 1.5sn debounce sonrası onReconnect çağırır", () => {
  const onReconnect = jest.fn();
  renderHook(() => useNetworkReachability(onReconnect));
  const cb = lastListener();

  cb({ isConnected: true });
  expect(onReconnect).not.toHaveBeenCalled(); // debounce dolmadan tetiklenmez
  jest.advanceTimersByTime(1500);
  expect(onReconnect).toHaveBeenCalledTimes(1);
});

it("aynı 'connected' durumu tekrar yayınlanırsa TEKRAR tetiklenmez", () => {
  const onReconnect = jest.fn();
  renderHook(() => useNetworkReachability(onReconnect));
  const cb = lastListener();

  cb({ isConnected: true });
  jest.advanceTimersByTime(1500);
  cb({ isConnected: true }); // aynı durum → atlanır
  jest.advanceTimersByTime(1500);
  expect(onReconnect).toHaveBeenCalledTimes(1);
});

it("bağlantı KESİLİNCE (isConnected=false) onReconnect çağrılmaz", () => {
  const onReconnect = jest.fn();
  renderHook(() => useNetworkReachability(onReconnect));
  const cb = lastListener();

  cb({ isConnected: false });
  jest.advanceTimersByTime(5000);
  expect(onReconnect).not.toHaveBeenCalled();
});

it("unmount'ta bekleyen debounce timer'ı iptal edilir (tetiklenmez)", () => {
  const onReconnect = jest.fn();
  const { unmount } = renderHook(() => useNetworkReachability(onReconnect));
  const cb = lastListener();

  cb({ isConnected: true }); // timer başlat
  unmount();                 // debounce dolmadan sök
  jest.advanceTimersByTime(1500);
  expect(onReconnect).not.toHaveBeenCalled();
});
