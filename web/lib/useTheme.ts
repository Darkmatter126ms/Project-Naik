"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "naik_theme";

function applyTheme(t: Theme) {
  try {
    if (t === "light") {
      document.documentElement.dataset.theme = "light";
    } else {
      delete document.documentElement.dataset.theme;
    }
  } catch { /* SSR guard */ }
}

export function useTheme(): [Theme, () => void] {
  const [theme, setThemeState] = useState<Theme>("dark");

  // Hydrate from localStorage after mount (avoids SSR mismatch).
  useEffect(() => {
    try {
      const stored = localStorage.getItem(KEY) as Theme | null;
      const resolved: Theme = stored === "light" ? "light" : "dark";
      setThemeState(resolved);
      applyTheme(resolved);
    } catch { /* ignore */ }
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
      applyTheme(next);
      return next;
    });
  }, []);

  return [theme, toggle];
}
