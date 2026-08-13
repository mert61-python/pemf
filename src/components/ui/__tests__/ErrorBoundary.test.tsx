// Author: mertaygn, cglrgrkn
/**
 * ErrorBoundary (audit B-3.2): bir ekran çökse bile BEYAZ EKRAN yerine kurtarılabilir kart
 * gösterilmeli (tıbbi cihazda donup kalma önlenir). Component-render testi (RNTL).
 */
import React from "react";
import { Text } from "react-native";
import { render } from "@testing-library/react-native";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";

function Boom(): React.ReactElement {
  throw new Error("test-patlama");
}

describe("ErrorBoundary", () => {
  it("çocuk hata atınca kurtarma kartını + hata mesajını gösterir", () => {
    jest.spyOn(console, "error").mockImplementation(() => {}); // React'in hata log'unu bastır
    const { getByText } = render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );
    expect(getByText("Beklenmeyen bir hata oluştu")).toBeTruthy();
    expect(getByText("Tekrar Dene")).toBeTruthy();
    expect(getByText("test-patlama")).toBeTruthy();
  });

  it("hata yoksa çocukları normal render eder", () => {
    const { getByText, queryByText } = render(
      <ErrorBoundary>
        <Text>Normal içerik</Text>
      </ErrorBoundary>
    );
    expect(getByText("Normal içerik")).toBeTruthy();
    expect(queryByText("Beklenmeyen bir hata oluştu")).toBeNull();
  });
});
