// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · bağlantı rozeti ("CANLI" / "OFFLINE") iki dilde.
 * Ekran görüntüsü taramasında (05b) EN'de Türkçe "CANLI" kaldığı görüldü: tek sözcüklü büyük harf dizgisi çıkarıcıda sabit adı sanılıyordu
 * (`scripts/i18n/cikar_ts.cjs` düzeltildi, P1-A3). Burada: TR değerleri göç öncesiyle BAYT BAYT aynı, EN doğru, iki ekran anahtarı GERÇEKTEN kullanıyor.
 */
import { readFileSync } from "fs";
import { join } from "path";
import i18n from "i18next";
import { act } from "react";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const kaynak = (rel: string) => readFileSync(join(__dirname, "..", rel), "utf8");

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("Türkçe: rozet metinleri göç öncesiyle aynı (CANLI / OFFLINE)", () => {
  expect(i18n.t("ana.rozetCanli")).toBe("CANLI");
  expect(i18n.t("ana.rozetCevrimdisi")).toBe("OFFLINE");
  expect(i18n.t("sensor.rozetCanli")).toBe("CANLI");
});

it("İngilizce: CANLI → LIVE, OFFLINE aynı", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  expect(i18n.t("ana.rozetCanli")).toBe("LIVE");
  expect(i18n.t("ana.rozetCevrimdisi")).toBe("OFFLINE");
  expect(i18n.t("sensor.rozetCanli")).toBe("LIVE");
});

it("ekranlar rozet metnini katalogdan alır (düz 'CANLI' / 'OFFLINE' dizgisi YOK)", () => {
  const ana = kaynak("DashboardScreen.tsx");
  const sensor = kaynak("SensorMonitorScreen.tsx");
  expect(ana).toContain('t("ana.rozetCanli")');
  expect(ana).toContain('t("ana.rozetCevrimdisi")');
  expect(sensor).toContain('t("sensor.rozetCanli")');
  // koşullu ifade dalı olarak düz dizgi (`? "CANLI" :` / `: "OFFLINE"}`) kalmamış (yorum satırlarındaki anma serbest)
  expect(ana).not.toMatch(/[?:]\s*"(CANLI|OFFLINE)"/);
  expect(sensor).not.toMatch(/[?:]\s*"CANLI"/);
});
