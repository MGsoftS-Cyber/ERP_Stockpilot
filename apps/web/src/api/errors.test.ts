import { describe, expect, it } from "vitest";

import { getApiErrorMessage } from "./errors";

describe("getApiErrorMessage", () => {
  it("keeps nested serializer fields readable", () => {
    const error = {
      isAxiosError: true,
      response: { data: { error: { detail: { lines: [{ quantity: ["Must be positive"] }] } } } },
    };
    expect(getApiErrorMessage(error)).toBe("lines[0].quantity: Must be positive");
  });
  it("returns a normal Error message", () => {
    expect(getApiErrorMessage(new Error("Connection failed"))).toBe("Connection failed");
  });

  it("returns a safe fallback for unknown values", () => {
    expect(getApiErrorMessage(null)).toBe("An unexpected error occurred.");
  });
});
