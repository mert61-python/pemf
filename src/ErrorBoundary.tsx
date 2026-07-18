import React from "react";
import { LINKS } from "./config";

/* Kök hata sınırı: bir render hatası tüm launcher'ı boş beyaz pencereye çevirmesin.
   Inline stil (Tailwind değil) → CSS/tema yüklenmese bile kurtarma ekranı GÖRÜNÜR. */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    // Geliştirici görünürlüğü (kullanıcıya ham hata gösterilmez).
    console.error("PEMF Vet Client render hatası:", error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          gap: 16,
          padding: 24,
          textAlign: "center",
          fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif",
          color: "#e5e7eb",
          background: "#0b0f14",
        }}
      >
        <div style={{ fontSize: 18, fontWeight: 700 }}>PEMF Vet</div>
        <div style={{ fontSize: 14, opacity: 0.8, maxWidth: 420, lineHeight: 1.5 }}>
          Beklenmeyen bir hata oluştu. / An unexpected error occurred.
        </div>
        <button
          onClick={() => location.reload()}
          style={{
            padding: "8px 20px",
            borderRadius: 10,
            border: "1px solid rgba(45,212,191,0.35)",
            background: "rgba(20,184,166,0.14)",
            color: "#5eead4",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          Yeniden dene / Retry
        </button>
        <a href={LINKS.support} style={{ fontSize: 12, color: "#6b7280", textDecoration: "none" }}>
          Destek / Support
        </a>
      </div>
    );
  }
}
