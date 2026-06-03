import React, { createContext, useContext, useState, ReactNode, useEffect } from "react";
import { StyleSheet, Text, View, Animated } from "react-native";
import { CheckCircle, AlertCircle, Info } from "lucide-react-native";
import { colors, radius, spacing, typography } from "@/theme/tokens";

type ToastType = "success" | "error" | "info";

interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const opacity = new Animated.Value(0);
  const translateY = new Animated.Value(-20);

  const showToast = (message: string, type: ToastType = "info") => {
    const newToast = { id: Math.random().toString(), message, type };
    setToast(newToast);

    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 300, useNativeDriver: true }),
      Animated.spring(translateY, { toValue: 20, useNativeDriver: true })
    ]).start();

    setTimeout(() => {
      Animated.parallel([
        Animated.timing(opacity, { toValue: 0, duration: 300, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: -20, duration: 300, useNativeDriver: true })
      ]).start(() => setToast(null));
    }, 3000);
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toast && (
        <Animated.View style={[styles.toastContainer, { opacity, transform: [{ translateY }] }]}>
          <View style={[styles.toast, styles[toast.type]]}>
            {toast.type === "success" && <CheckCircle color={colors.white} size={20} />}
            {toast.type === "error" && <AlertCircle color={colors.white} size={20} />}
            {toast.type === "info" && <Info color={colors.white} size={20} />}
            <Text style={styles.message}>{toast.message}</Text>
          </View>
        </Animated.View>
      )}
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  toastContainer: {
    position: "absolute",
    top: 40,
    left: 0,
    right: 0,
    alignItems: "center",
    zIndex: 9999
  },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    gap: spacing.md,
    shadowColor: "#000",
    shadowOpacity: 0.3,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 5
  },
  success: { backgroundColor: colors.success },
  error: { backgroundColor: colors.danger },
  info: { backgroundColor: colors.primary },
  message: {
    color: colors.white,
    fontSize: typography.body,
    fontWeight: "700"
  }
});
