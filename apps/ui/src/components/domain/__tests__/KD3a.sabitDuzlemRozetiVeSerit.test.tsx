// Author: mertaygn, cglrgrkn
/**
 * KD-3a (B-KD3a.1, tezgâh 2026-11-11): SABİT DÜZLEM kipinde AI Pro rozeti / şeridi / onay penceresi ArUco metnine düşüyordu —
 * "Konum ölçülemedi — kabin işareti (arka duvardaki kare kod) kadrajda görünmüyor" (sahibin ekran görüntüleri: hazırlıkta taban ayarı
 * yanlışken ve onay penceresinde konum GEÇERLİYKEN). Artık: ölçüldüyse "kabin kalibrasyonuyla ölçüldü ✓", kapı FİZİKSEL nedenle
 * kestiyse sunucunun eylem metni, ikisi yoksa "numune aranıyor". ArUco kipi (aruco_pnp / pixel) DEĞİŞMEDİ (karşıt).
 * ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => ({})),
  apiPost: jest.fn(async () => ({ status: "success" })),
  authHeaders: jest.fn(() => ({})),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => false),
  AI_TIMEOUT_MS: 120000,
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" },
  getClientInstanceId: jest.fn(async () => "web-id"),
}));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: null, wsConnected: true, aiVisionData: undefined, aiVisionFresh: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperator: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("expo-camera", () => {
  const React2 = require("react");
  return { CameraView: React2.forwardRef(() => null), useCameraPermissions: () => [{ granted: true }, jest.fn()] };
});

import { act, render } from "@testing-library/react-native";
import React from "react";

import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

import { asamaMetniArastirma } from "../AiProPanel";
import { AiSpecApprovalModal } from "../AiSpecApprovalModal";
import { KalibrasyonRozeti } from "../aipro/KalibrasyonRozeti";

const depo = { setItem: async () => undefined };
const EYLEM_TR = "Kamera oynamış olabilir … yeniden kalibre edin.";
const EYLEM_EN = "The camera may have moved … recalibrate.";

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}

function metin(u: ReturnType<typeof render>): string {
  const topla = (n: any): string => {
    if (n == null) return "";
    if (typeof n === "string") return n;
    if (Array.isArray(n)) return n.map(topla).join("");
    return topla(n.children);
  };
  return topla(u.toJSON());
}

const SERIT = {
  ozne: "petri plakası",
  ozneIpucu: "",
  hedefEtiketi: "Kuyu",
  hedefEtiketiKucuk: "kuyu",
  ozneVar: true,
  localized: false,
  hedefSayisi: 0,
  guvenYuzde: 0,
  gecikmeIpucu: "",
};

describe("KD-3a sabit düzlem rozeti", () => {
  it("TR: ölçüldü / kapı eylemi / numune aranıyor — ArUco metni YOK", () => {
    const olc = metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" localized />));
    expect(olc).toBe("3B konum: kabin kalibrasyonuyla ölçüldü ✓");
    const eng = metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" kapiEylem={EYLEM_TR} />));
    expect(eng).toBe(`Konum ölçülemedi — ${EYLEM_TR}`);
    const bek = metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" />));
    expect(bek).toBe("3B konum: kabin kalibrasyonuyla ölçülecek — numune aranıyor.");
    for (const m of [olc, eng, bek]) expect(m).not.toContain("kare kod");
  });

  it("EN: measured / gate action / looking for the sample", async () => {
    await enYap();
    expect(metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" localized />))).toBe(
      "3D position: measured with the cabin calibration ✓",
    );
    expect(metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" kapiEylem={EYLEM_EN} />))).toBe(
      `Position not measured — ${EYLEM_EN}`,
    );
    expect(metin(render(<KalibrasyonRozeti yontem="sabit_duzlem" />))).toBe(
      "3D position: will be measured with the cabin calibration — looking for the sample.",
    );
  });

  it("KARŞIT: ArUco kipi değişmedi (aruco_pnp doğrulandı, pixel kare kod uyarısı)", () => {
    expect(metin(render(<KalibrasyonRozeti yontem="aruco_pnp" />))).toBe("3B konum: kabin işaretiyle doğrulandı ✓");
    expect(metin(render(<KalibrasyonRozeti yontem="pixel" kapiEylem={EYLEM_TR} />))).toContain("kare kod");
  });

  it("onay penceresi (araştırma, sabit düzlem): rozet 'kabin kalibrasyonuyla ölçüldü' — 'kabin işareti' DEĞİL", () => {
    const u = render(
      <AiSpecApprovalModal
        visible
        specs={{ organ_id: 1, duration_minutes: 20, coil_ids: [1], D: [0.3], P: [0], model: "petri", target_label: "Kuyu B5" } as any}
        meta={{ x_mm: 103.7, y_mm: -172, z_mm: 35.7, reliability: 0.99, method: "sabit_duzlem" } as any}
        onApprove={jest.fn()}
        onReject={jest.fn()}
        onDismiss={jest.fn()}
      />,
    );
    const m = metin(u);
    expect(m).toContain("3B konum: kabin kalibrasyonuyla ölçüldü ✓");
    expect(m).not.toContain("kare kod");
  });
});

describe("KD-3a araştırma şeridi (sabit düzlem)", () => {
  it("TR: kapı FİZİKSEL nedenle kestiyse NEDEN + EYLEM (plaka bulundu, konum kalibrasyonda kesildi)", () => {
    expect(asamaMetniArastirma({ ...SERIT, yontem: "sabit_duzlem", kapiEylem: EYLEM_TR })).toBe(
      `⚠️ Kuyu konumu ölçülemedi — ${EYLEM_TR}`,
    );
  });

  it("EN: gate action", async () => {
    await enYap();
    expect(asamaMetniArastirma({ ...SERIT, yontem: "sabit_duzlem", kapiEylem: EYLEM_EN })).toBe(
      `⚠️ Kuyu position not measured — ${EYLEM_EN}`,
    );
  });

  it("sabit düzlemde eylem yokken hedef adayı olsa da ArUco 'kabin işareti' metni ÇIKMAZ; ArUco kipinde AYNEN çıkar (karşıt)", () => {
    const duz = asamaMetniArastirma({ ...SERIT, hedefSayisi: 3, yontem: "sabit_duzlem", kapiEylem: "" });
    expect(duz).not.toContain("kare kod");
    expect(duz).toContain("aranıyor");
    expect(asamaMetniArastirma({ ...SERIT, hedefSayisi: 3, yontem: "pixel" })).toContain("kare kod");
  });

  it("konumlandıysa (eylem kalmış olsa da) 'konumlandı'", () => {
    expect(
      asamaMetniArastirma({ ...SERIT, localized: true, guvenYuzde: 99, yontem: "sabit_duzlem", kapiEylem: EYLEM_TR }),
    ).toContain("konumlandı");
  });
});
