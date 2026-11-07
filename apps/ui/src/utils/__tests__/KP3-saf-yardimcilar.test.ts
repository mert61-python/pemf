/**
 * KP-3 C · saf yardımcıların kapsanmayan kolları — her test bir DAVRANIŞ iddiası:
 *  - modelleriAl: profil yok / bilinmiyor → kedi (eski davranış); evcil hayvan sahibine AI Pro modeli YOK (boş liste kedi'ye düşmez).
 *  - clampTherapyParams: verilmeyen (null / undefined) parametre sonuçta YER ALMAZ ve uyarı üretmez (0'a çekilip cihaza gitmez).
 *  - sahneSayfalari: anahtarı olmayan / bozuk panel atlanır (çökme / "undefined" uri yok).
 *  - takipSerisiKur: modül adı taşımayan kayıtlardan seri KURULMAZ (null — boş grafik çizilmez).
 * GERÇEK: modüllerin kendisi (sahte yok).
 */
import { modelleriAl } from "@/components/domain/aiProProfilleri";
import { clampTherapyParams } from "@/services/therapyLimits";
import { sahneSayfalari } from "@/utils/gorselSahneSayfalari";
import { takipSerisiKur } from "@/utils/takipSerisi";

it("modelleriAl: profil yok / bilinmiyor → kedi; evcil hayvan sahibine model yok", () => {
  expect(modelleriAl(null)).toEqual(["kedi"]);
  expect(modelleriAl(undefined)).toEqual(["kedi"]);
  expect(modelleriAl("bilinmeyen_profil")).toEqual(["kedi"]);
  expect(modelleriAl("pet_owner")).toEqual([]);
  expect(modelleriAl("researcher")).toEqual(["fantom", "petri"]);
});

it("clampTherapyParams: verilmeyen parametre sonuçta yer almaz ve uyarı üretmez", () => {
  const r = clampTherapyParams({ freq: 40, phase: undefined, duration: null as unknown as number });
  expect(r.values).toEqual({ freq: 40 });
  expect(r.warnings).toEqual([]);
});

it("sahneSayfalari: anahtarsız / bozuk panel atlanır", () => {
  const s = sahneSayfalari({
    paneller: [null, { ad: "anahtarsız", image_base64: "QQ==" }, { k: 7, image_base64: "QQ==" }, { k: "02_sonuc", ad: "Sonuç", image_base64: "QkI=" }],
  } as never, null);
  expect(s.map((p) => p.k)).toEqual(["02_sonuc"]);
  expect(s[0].uri).toContain("QkI=");
});

it("takipSerisiKur: modül adı taşımayan kayıtlardan seri kurulmaz", () => {
  expect(takipSerisiKur([
    // güven değeri VAR (modül kapısı olmasa varsayılan ölçütle seri kurulabilirdi) — modül adı YOK
    { created_at: "2026-11-01T10:00:00", confidence: 0.8, result_detail: { fgs_total: 3 } },
    { created_at: "2026-11-02T10:00:00", confidence: 0.6, result_detail: { fgs_total: 2 } },
  ] as never)).toBeNull();
});
