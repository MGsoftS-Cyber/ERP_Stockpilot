import { describe, expect, it } from "vitest";
import { translate } from "./index";
import messages from "./messages.json";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

describe("UI language contract", () => {
  it("translates English, French, Arabic and normalized enum labels", () => {
    expect(translate("Products", "en")).toBe("Products");
    expect(translate("Products", "fr")).toBe("Produits");
    expect(translate("Products", "ar")).toBe("المنتجات");
    expect(translate("PARTIALLY_RECEIVED", "fr")).toBe("Partiellement reçu");
    expect(translate("SKU-123", "ar")).toBe("SKU-123");
  });
  it("contains both translations for every static JSX translation key", () => {
    const catalog: Record<string, string[]> = messages;
    function check(directory: string) {
      for (const file of readdirSync(directory, { withFileTypes: true })) {
        const path = resolve(directory, file.name);
        if (file.isDirectory()) check(path);
        else if (file.name.endsWith(".tsx")) {
          for (const match of readFileSync(path, "utf8").matchAll(/\bt\("([^"\n]+)"\)/g)) {
            expect(catalog[match[1]], `${file.name}: ${match[1]}`).toHaveLength(2);
          }
        }
      }
    }
    check(resolve("src"));
  });
});
