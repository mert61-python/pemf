// Author: mertaygn, cglrgrkn
/**
 * AI ÖNERİSİ ONAY MODALI (2026-08-06, sahip kararı: "sert kapı").
 *
 * Kilitlenen davranışlar hasta güvenliği içindir:
 *   * Onay ve red AYRI eylemlerdir; kapatmak REDDETMEK DEĞİLDİR (sessiz "reddedildi" kaydı yanıltır).
 *   * Red GEREKÇESİZ gönderilemez (denetim izi boş kalmasın).
 *   * Düşük lokalizasyon güveni hekime AÇIKÇA söylenir.
 */
import React from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { AiSpecApprovalModal, type AiProposalSpecs } from "../AiSpecApprovalModal";

const SPECS: AiProposalSpecs = {
  organ_id: 2,
  duration_minutes: 20,
  coil_ids: [1, 2, 3, 4, 5, 6, 7],
  D: [0.42, 0.31, 0, 0.18, 0, 0.25, 0.1],
  P: [0, 45, 90, 135, 180, 225, 270],
  e_field: 0.0731,
};

const setup = (over: Partial<React.ComponentProps<typeof AiSpecApprovalModal>> = {}) => {
  const onApprove = jest.fn();
  const onReject = jest.fn();
  const onDismiss = jest.fn();
  const utils = render(
    <AiSpecApprovalModal
      visible
      specs={SPECS}
      meta={{ reliability: 0.9 }}
      organName="Böbrek"
      onApprove={onApprove}
      onReject={onReject}
      onDismiss={onDismiss}
      {...over}
    />,
  );
  return { ...utils, onApprove, onReject, onDismiss };
};

describe("AiSpecApprovalModal", () => {
  it("spec yokken hiçbir şey render etmez", () => {
    const { toJSON } = setup({ specs: null });
    expect(toJSON()).toBeNull();
  });

  it("önerilen parametreleri gösterir (organ, süre, sürülen bobin)", () => {
    const { getByText } = setup();
    expect(getByText("Böbrek")).toBeTruthy();
    expect(getByText("20 dk")).toBeTruthy();
    expect(getByText("5/7")).toBeTruthy();   // duty>0 olan 5 bobin
  });

  it("duty'yi YÜZDE olarak gösterir (model 0-1 üretir, hekim klinik birimde okur)", () => {
    const { getByText, getAllByText } = setup();
    expect(getByText("%42.0")).toBeTruthy();
    expect(getByText("%31.0")).toBeTruthy();
    // Sürülmeyen bobinler (D=0) da listelenir → hangi bobinin KAPALI olduğu görünür.
    expect(getAllByText("%0.0")).toHaveLength(2);
  });

  it("Onayla basılınca onApprove çağrılır", () => {
    const { getByLabelText, onApprove, onReject } = setup();
    fireEvent.press(getByLabelText("Öneriyi onayla ve seansı başlat"));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onReject).not.toHaveBeenCalled();
  });

  it("KAPATMAK reddetmek DEĞİLDİR — onReject çağrılmaz", () => {
    const { getByLabelText, onReject, onDismiss } = setup();
    fireEvent.press(getByLabelText("Kapat"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onReject).not.toHaveBeenCalled();
  });

  it("Reddet GEREKÇE ister — boşken gönderilemez", () => {
    const { getByLabelText, onReject } = setup();
    fireEvent.press(getByLabelText("Öneriyi reddet"));
    fireEvent.press(getByLabelText("Reddi onayla"));
    expect(onReject).not.toHaveBeenCalled();
  });

  it("gerekçe yazılınca red gönderilir ve gerekçe taşınır", () => {
    const { getByLabelText, onReject } = setup();
    fireEvent.press(getByLabelText("Öneriyi reddet"));
    fireEvent.changeText(getByLabelText("Red gerekçesi"), "Lokalizasyon hatalı");
    fireEvent.press(getByLabelText("Reddi onayla"));
    expect(onReject).toHaveBeenCalledWith("Lokalizasyon hatalı");
  });

  it("DÜŞÜK lokalizasyon güvenini açıkça uyarır", () => {
    const { getByText } = setup({ meta: { reliability: 0.3 } });
    expect(getByText(/DÜŞÜK, konumu doğrulayın/)).toBeTruthy();
  });

  it("yüksek güvende uyarı YOK", () => {
    const { queryByText } = setup({ meta: { reliability: 0.95 } });
    expect(queryByText(/DÜŞÜK/)).toBeNull();
  });

  it("işlem sürerken onay butonu devre dışı (çift başlatma yok)", () => {
    const { getByLabelText, onApprove } = setup({ busy: true });
    fireEvent.press(getByLabelText("Öneriyi onayla ve seansı başlat"));
    expect(onApprove).not.toHaveBeenCalled();
  });
});
