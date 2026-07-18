import { useEffect } from "react";

/* Uygulama-içi onay/uyarı modalı (native window.confirm/alert yerine — tutarlı stil + Escape/Enter +
   Tauri-güvenilir). cancelText yoksa = yalnız-bilgi (alert) modu. */
export default function ConfirmModal({
  message,
  confirmText,
  cancelText,
  danger,
  onConfirm,
  onCancel,
}: {
  message: string;
  confirmText: string;
  cancelText?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      else if (e.key === "Enter") onConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, onConfirm]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: "oklch(8% 0.03 264 / 0.68)", backdropFilter: "blur(6px)" }}
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="card glow-ring relative w-full max-w-sm p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-sm leading-relaxed text-fg/90">{message}</p>
        <div className="mt-6 flex justify-end gap-2">
          {cancelText && (
            <button className="btn-ghost !py-2 text-sm" onClick={onCancel}>
              {cancelText}
            </button>
          )}
          <button
            autoFocus
            className="btn-primary !py-2 text-sm"
            style={danger ? { background: "var(--color-danger)", color: "#fff" } : undefined}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
