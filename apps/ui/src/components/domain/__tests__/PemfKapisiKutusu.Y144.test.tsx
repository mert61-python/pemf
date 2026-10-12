// Author: mertaygn, cglrgrkn
/**
 * Y144 (sahip 2026-10-13) — sürülemez sonuçta canlı E göstergesi ve "dozu en çok belirleyen" açıklaması KURULMAZ (backend);
 * arayüz bunun NEDENİNİ söyler: operatör AI Hub analizinden sonra seansta canlı E barını göremeyince "bozuk" sanmasın.
 * Neden metni kutunun kendi hükmünden türer (`surulebilir`); alan yoksa (eski backend) kutu hiç çizilmez (değişmedi).
 * ⚠️ Beklenen metin BURADA sabittir.
 */
import { render } from "@testing-library/react-native";
import React from "react";

import { PemfKapisiKutusu } from "../PemfKapisiKutusu";

const NEDEN = "Canlı E göstergesi ve “dozu en çok belirleyen” açıklaması bu sonuçtan kurulmadı";

it("KRİTİK Y144: sürülemez sonuçta (kabin konumu GEÇERLİ ama fantom güvenilmez) neden SATIRI görünür", () => {
  const u = render(
    <PemfKapisiKutusu
      model="fantom"
      reliable={false}
      kapi={{
        surulebilir: false,
        pemf_gecerli: true,
        nedenler: ["guvenilir_degil"],
        mesajlar: [{ kod: "guvenilir_degil", metin: "Tümör tespiti güvenilir değil — yeniden çekin." }],
        varsayimlar: [],
      }}
    />,
  );
  const satir = u.getByTestId("pemf-kapisi-baglam-kurulmadi");
  const metin = Array.isArray(satir.props.children) ? satir.props.children.join("") : String(satir.props.children);
  expect(metin).toContain(NEDEN);
  expect(metin).toContain("sürülebilir değil");
});

it("KRİTİK Y144: PEMF girdisi GEÇERSİZ sonuçta da neden satırı görünür (petri)", () => {
  const u = render(
    <PemfKapisiKutusu
      model="petri"
      kapi={{ surulebilir: false, pemf_gecerli: false, nedenler: ["pemf_gecersiz"], mesajlar: [], varsayimlar: [] }}
    />,
  );
  const satir = u.getByTestId("pemf-kapisi-baglam-kurulmadi");
  const metin = Array.isArray(satir.props.children) ? satir.props.children.join("") : String(satir.props.children);
  expect(metin).toContain("açıklaması bu sonuçtan üretilmedi");
  expect(metin).toContain("sürülebilir değil");
  expect(metin).not.toContain("Canlı E"); // petri canlı E bağlamı kurmaz — satır olmayan bir şeyi "kurulmadı" demez
});

it("KARŞIT Y144: sürülebilir sonuçta neden satırı YOK", () => {
  const u = render(
    <PemfKapisiKutusu
      model="fantom"
      reliable
      kapi={{ surulebilir: true, pemf_gecerli: true, nedenler: [], mesajlar: [], varsayimlar: [] }}
    />,
  );
  expect(u.queryByTestId("pemf-kapisi-baglam-kurulmadi")).toBeNull();
});
