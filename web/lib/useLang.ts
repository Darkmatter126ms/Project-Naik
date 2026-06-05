"use client";

/**
 * lib/useLang.ts
 *
 * Persistent language hook. Reads from / writes to localStorage so the
 * toggle carries across page navigations without a context provider or URL
 * query param. Defaults to "id" (Bahasa Indonesia) on first visit.
 *
 * Usage in any page:
 *   const [lang, setLang] = useLang();
 *   const t = COPY[lang];
 */

import { useCallback, useEffect, useState } from "react";
import type { Lang } from "./types";

const STORAGE_KEY = "naik_lang";

export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLangState] = useState<Lang>("id");

  // Hydrate from localStorage after mount (avoids SSR mismatch).
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "id" || stored === "en") setLangState(stored);
    } catch {
      /* localStorage unavailable in some sandboxed environments */
    }
  }, []);

  const setLang = useCallback((l: Lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch { /* ignore */ }
    setLangState(l);
  }, []);

  return [lang, setLang];
}
