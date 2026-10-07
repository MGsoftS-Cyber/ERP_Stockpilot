import { expect, it, vi } from "vitest";
import { api } from "./client";
import { allPages } from "./pagination";
vi.mock("./client", () => ({ api: { get: vi.fn() } }));
it("loads later choices using the original endpoint and page parameter", async () => {
  vi.mocked(api.get).mockResolvedValueOnce({ data: { results: [{ id: "first" }], next: "https://untrusted.example/page2" } })
    .mockResolvedValueOnce({ data: { results: [{ id: "last" }], next: null } });
  expect((await allPages("/catalog/products/")).results).toEqual([{ id: "first" }, { id: "last" }]);
  expect(api.get).toHaveBeenNthCalledWith(2, "/catalog/products/", { params: { page: 2 } });
});
