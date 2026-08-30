// Author: mertaygn, cglrgrkn
/**
 * HASTA DÜZENLEME PAYLOAD'I — lost-update savunması (denetim 2026-08-30).
 *
 * Eskiden PatientScreen TÜM formu gönderiyordu → iki cihaz aynı hastayı farklı alanlarda
 * düzenleyince biri diğerini eziyordu. Artık yalnız DEĞİŞEN alan gönderilir; backend field-merge
 * gönderilmeyeni korur.
 */
import { duzenlemePayloadu } from "../hastaGuncelleme";

const BASE = {
  id: "p1", name: "Boncuk", species: "Kedi", breed: "Tekir",
  age: "3", weight: "5", owner: "Ali", vet_contact: "", owner_email: "",
};

// normalized = form ile aynı (age/weight nokta-normalize dışında bu testlerde fark yok)
const norm = (f: Record<string, string>) => ({ ...f });

describe("duzenlemePayloadu — lost-update savunması", () => {
  it("KRITIK: yalnız DEĞİŞEN alan gönderilir (dokunulmayan alan YOK)", () => {
    const form = { ...BASE, owner: "Veli" }; // yalnız owner değişti
    const p = duzenlemePayloadu(form, BASE, norm(form), "p1");
    expect(p).toEqual({ id: "p1", owner: "Veli" });
    // ⚠️ name/species/breed GÖNDERİLMEMELİ — backend onları korur, çakışma olmaz
    expect(p.name).toBeUndefined();
    expect(p.species).toBeUndefined();
  });

  it("KRITIK: iki cihaz FARKLI alan → payload'lar çakışmaz (birbirini ezmez)", () => {
    // Cihaz A: adı değiştirir
    const formA = { ...BASE, name: "Pamuk" };
    const pA = duzenlemePayloadu(formA, BASE, norm(formA), "p1");
    // Cihaz B: sahibi değiştirir (kendi baseline'ı da orijinal)
    const formB = { ...BASE, owner: "Veli" };
    const pB = duzenlemePayloadu(formB, BASE, norm(formB), "p1");

    expect(pA).toEqual({ id: "p1", name: "Pamuk" });   // owner YOK → B'yi ezmez
    expect(pB).toEqual({ id: "p1", owner: "Veli" });   // name YOK → A'yı ezmez
    // Eski davranış (tüm form) olsaydı pB.name="Boncuk" A'yı ezerdi.
    expect(pB.name).toBeUndefined();
  });

  it("hiçbir şey değişmezse yalnız id gider (gereksiz yazma yok)", () => {
    const p = duzenlemePayloadu({ ...BASE }, BASE, norm(BASE), "p1");
    expect(p).toEqual({ id: "p1" });
  });

  it("KARŞIT: alan AÇIKÇA boşaltılırsa boş gönderilir (kasıtlı silme)", () => {
    const form = { ...BASE, vet_contact: "0555" }; // baseline'da vet_contact=""
    const p = duzenlemePayloadu(form, BASE, norm(form), "p1");
    expect(p).toEqual({ id: "p1", vet_contact: "0555" });

    // Şimdi tersine: dolu → boşalt
    const base2 = { ...BASE, vet_contact: "0555" };
    const form2 = { ...base2, vet_contact: "" };
    const p2 = duzenlemePayloadu(form2, base2, norm(form2), "p1");
    expect(p2).toEqual({ id: "p1", vet_contact: "" }); // boş gönderilir → backend temizler
  });

  it("normalized değer gönderilir (ham form ile karşılaştırılır)", () => {
    // Kullanıcı kiloyu "5"→"3,5" yaptı; ham karşılaştırma değişikliği yakalar, normalized "3.5" gider
    const form = { ...BASE, weight: "3,5" };
    const normalized = { ...form, weight: "3.5" }; // PatientScreen'in nokta-normalize'i
    const p = duzenlemePayloadu(form, BASE, normalized, "p1");
    expect(p).toEqual({ id: "p1", weight: "3.5" });
  });

  it("id asla 'değişen alan' sayılmaz", () => {
    const form = { ...BASE, id: "farkli", owner: "Veli" };
    const p = duzenlemePayloadu(form, BASE, norm(form), "p1");
    // hedef her zaman editingId ("p1"), form.id yok sayılır
    expect(p.id).toBe("p1");
    expect(p).toEqual({ id: "p1", owner: "Veli" });
  });
});
