// Translation boundary: an English key selects French/Arabic UI text from messages.json.
// useLanguage notifies React subscribers; setLanguage persists this browser’s choice.
// Business data, endpoint names and database enums retain their original values.
// UI messages are separate from product names, notes and other customer data.
import { useSyncExternalStore } from "react";
import messages from "./messages.json";
export type Language = "en" | "fr" | "ar";
const listeners = new Set<() => void>();
let language: Language = "en";
try {
  const saved = localStorage.getItem("stockpilot.language");
  if (saved === "fr" || saved === "ar") language = saved;
} catch {
  /* Storage is optional. */
}
export const getLanguage = () => language;
export function setLanguage(value: Language) {
  language = value;
  try {
    localStorage.setItem("stockpilot.language", value);
  } catch {
    /* Keep the in-memory choice. */
  }
  listeners.forEach((listener) => listener());
}
export function useLanguage() {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, getLanguage);
}
export function translate(key: string, locale: Language, values: Record<string, string | number> = {}) {
  const normalized = key.toLowerCase().replaceAll("_", " ");
  const catalog: Record<string, string[]> = messages;
  const canonical = Object.keys(catalog).find((item) => item.toLowerCase() === normalized);
  let result = locale === "en" ? key : (catalog[canonical ?? key]?.[locale === "fr" ? 0 : 1] ?? key);
  for (const [name, value] of Object.entries(values)) result = result.replaceAll(`{${name}}`, String(value));
  return result;
}
export const t = (key: string, values?: Record<string, string | number>) => translate(key, language, values);
export const formatDate = (date: string) => new Date(date).toLocaleString(language);
