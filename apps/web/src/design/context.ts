import { createContext, useContext } from "react";
export type Tokens = {
  primary: string;
  secondary: string;
  background: string;
  radius: number;
  font_size: number;
  mode: "light" | "dark";
  density: "standard" | "compact";
};
export const defaults: Tokens = {
  primary: "#1f5d50",
  secondary: "#d58b34",
  background: "#f7f9f8",
  radius: 10,
  font_size: 14,
  mode: "light",
  density: "standard",
};
export const DesignContext = createContext<{
  settings: Tokens;
  revision: number;
  preview: (tokens: Tokens | null) => void;
}>({ settings: defaults, revision: 0, preview: () => {} });
export const useDesign = () => useContext(DesignContext);
