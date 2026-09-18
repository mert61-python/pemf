// Author: mertaygn, cglrgrkn
/**
 * HEKİM DEĞERLENDİRMESİ KONTROLLERİ (2026-08-06).
 * Klinik sözleşme: red/düzeltme GEREKÇESİZ gönderilemez; onay notsuz olabilir.
 */
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { AiReviewControls, ReviewBadge } from "../AiReviewControls";

const setup = (over: Partial<React.ComponentProps<typeof AiReviewControls>> = {}) => {
  const onSubmit = jest.fn();
  const utils = render(<AiReviewControls onSubmit={onSubmit} {...over} />);
  return { ...utils, onSubmit };
};

describe("AiReviewControls", () => {
  it("değerlendirilmemişken hekimi bilgilendirir", () => {
    const { getByText } = setup();
    expect(getByText(/değerlendirilmedi/i)).toBeTruthy();
  });

  it("Onayla notsuz gönderilebilir", () => {
    const { getByLabelText, onSubmit } = setup();
    fireEvent.press(getByLabelText("AI sonucunu onayla"));
    expect(onSubmit).toHaveBeenCalledWith("approved", "");
  });

  it("Reddet GEREKÇESİZ gönderilemez", () => {
    const { getByLabelText, onSubmit } = setup();
    fireEvent.press(getByLabelText("AI sonucunu reddet"));
    fireEvent.press(getByLabelText("Reddi kaydet"));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("gerekçe yazılınca red gönderilir", () => {
    const { getByLabelText, onSubmit } = setup();
    fireEvent.press(getByLabelText("AI sonucunu reddet"));
    fireEvent.changeText(getByLabelText("Red gerekçesi"), "Klinik bulgularla uyuşmuyor");
    fireEvent.press(getByLabelText("Reddi kaydet"));
    expect(onSubmit).toHaveBeenCalledWith("rejected", "Klinik bulgularla uyuşmuyor");
  });

  it("Düzelt AÇIKLAMASIZ gönderilemez", () => {
    const { getByLabelText, onSubmit } = setup();
    fireEvent.press(getByLabelText("AI sonucunu düzelt"));
    fireEvent.press(getByLabelText("Düzeltmeyi kaydet"));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("düzeltme hekimin teşhisini taşır", () => {
    const { getByLabelText, onSubmit } = setup();
    fireEvent.press(getByLabelText("AI sonucunu düzelt"));
    fireEvent.changeText(getByLabelText("Düzeltme açıklaması"), "İdiyopatik sistit");
    fireEvent.press(getByLabelText("Düzeltmeyi kaydet"));
    expect(onSubmit).toHaveBeenCalledWith("corrected", "İdiyopatik sistit");
  });

  it("verilmiş kararı kim/ne zaman ile gösterir", () => {
    const { getByText } = setup({
      status: "rejected", note: "Uyuşmuyor",
      reviewedBy: "dr@k.com", reviewedAt: "06.08.2026",
    });
    expect(getByText("Hekim reddetti")).toBeTruthy();
    expect(getByText("Uyuşmuyor")).toBeTruthy();
    expect(getByText("dr@k.com · 06.08.2026")).toBeTruthy();
  });

  it("gönderim sürerken buton devre dışı (çift kayıt yok)", () => {
    const { getByLabelText, onSubmit } = setup({ busy: true });
    fireEvent.press(getByLabelText("AI sonucunu onayla"));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("ReviewBadge", () => {
  it("değerlendirilmemişte HİÇBİR ŞEY göstermez (her kartta gürültü olmasın)", () => {
    expect(render(<ReviewBadge status="" />).toJSON()).toBeNull();
    expect(render(<ReviewBadge />).toJSON()).toBeNull();
  });

  it("karar verilmişse durumu gösterir", () => {
    expect(render(<ReviewBadge status="approved" />).getByText("Hekim onayladı")).toBeTruthy();
    expect(render(<ReviewBadge status="corrected" />).getByText("Hekim düzeltti")).toBeTruthy();
  });
});
