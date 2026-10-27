// Author: mertaygn, cglrgrkn
/**
 * A-65 (sahip) · D5.42 — sürüş kipi seçicisinde bipolar yeteneği YALNIZ backend'in bildirdiği `bipolarYetenek` alanından gelir.
 * ===========================================================================================================================
 * HEAD: alan yoksa yedek kural `id <= 5` (bobin 1-5 bipolar sayılıyordu) — yeteneği bobin NUMARASINDAN çıkarmak, donanım değişince
 * (sürücü kartı / bobin yerleşimi) sessizce yanlış düğme açar. Artık: alan `true` ise yetenekli; yoksa / `false` ise kilitli (bipolar
 * İSTENMEZ). Backend alanı her STM bobini için yayınlar (`apps/backend/servers/live_state.py` `bipolarYetenek`).
 * Gerçek bileşen; sahte yalnız `apiClient` (gövde kaydedici).
 */
const mockApiPost = jest.fn(async (..._a: unknown[]) => ({ status: "success" }));
jest.mock("@/services/apiClient", () => ({
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: async () => true,
}));

import { fireEvent, render } from "@testing-library/react-native";
import { SurusKipiSecici } from "@/components/domain/SurusKipiSecici";
import type { CoilStatus } from "@/types/domain";

const bobin = (id: number, ek: Partial<CoilStatus> = {}): CoilStatus => ({
  id, connected: true, running: false, frequencyHz: 0, dutyCycle: 0, magneticMt: 0, objectTemp: 0, ambientTemp: 0, currentA: 0, ...ek,
});

beforeEach(() => mockApiPost.mockClear());

test("KRİTİK: backend `bipolarYetenek` BİLDİRMEDİYSE hiçbir bobin bipolar sayılmaz (numaradan yetenek çıkarılmaz)", () => {
  const u = render(<SurusKipiSecici coils={[1, 2, 3, 4, 5, 6, 7].map((id) => bobin(id))} stmConnected />);
  for (const id of [1, 2, 3, 4, 5, 6, 7]) {
    const kutu = u.getByLabelText(new RegExp(`^Bobin ${id}, unipolar, sürücüsü yalnız unipolar`));
    expect(kutu.props.accessibilityState?.disabled).toBe(true);
  }
  fireEvent.press(u.getByLabelText(/^Bobin 1, unipolar/));
  expect(mockApiPost).not.toHaveBeenCalled();
});

test("KRİTİK: yetenek NUMARAYA değil ALANA bağlı — bobin 6 için `bipolarYetenek:true` bildirilirse kutusu açılır, bobin 1 `false` ise kilitli", () => {
  const coils = [1, 2, 3, 4, 5, 6, 7].map((id) => bobin(id, { bipolarYetenek: id === 6 }));
  const u = render(<SurusKipiSecici coils={coils} stmConnected />);
  expect(u.getByLabelText(/^Bobin 6, bipolar/).props.accessibilityState?.disabled).toBe(false);
  expect(u.getByLabelText(/^Bobin 1, unipolar, sürücüsü yalnız unipolar/).props.accessibilityState?.disabled).toBe(true);
});
