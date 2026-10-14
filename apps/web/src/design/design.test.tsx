// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../api/client";
import { DesignProvider } from "./DesignProvider";
import { DesignEditor } from "./DesignEditor";
import { defaults } from "./context";
import { setLanguage, t, useLanguage } from "../i18n";
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ selectedMembership: { organization: { id: "org-a" } } }),
}));
vi.mock("../api/client", () => ({ api: { get: vi.fn(), put: vi.fn() } }));
afterEach(() => {
  cleanup();
  setLanguage("en");
  vi.clearAllMocks();
});
function View() {
  useLanguage();
  return (
    <>
      <span>{t("Products")}</span>
      <DesignEditor canEdit />
    </>
  );
}
function mount() {
  vi.mocked(api.get).mockResolvedValue({ data: { settings: defaults, revision: 0, customized: false } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DesignProvider>
        <View />
      </DesignProvider>
    </QueryClientProvider>,
  );
}
it("changes language and document direction without altering domain data", async () => {
  mount();
  act(() => setLanguage("fr"));
  expect(screen.getByText("Produits")).toBeTruthy();
  act(() => setLanguage("ar"));
  expect(screen.getByText("المنتجات")).toBeTruthy();
  await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
  expect(document.documentElement.lang).toBe("ar");
  expect(localStorage.getItem("stockpilot.language")).toBe("ar");
});
it("opening and previewing never saves; explicit save sends the revision", async () => {
  mount();
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByLabelText("primary").getAttribute("value")).toBe(defaults.primary));
  expect(api.put).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("primary"), { target: { value: "#123456" } });
  fireEvent.click(screen.getByText("Preview"));
  expect(api.put).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Cancel preview"));
  expect((screen.getByLabelText("primary") as HTMLInputElement).value).toBe(defaults.primary);
  fireEvent.change(screen.getByLabelText("primary"), { target: { value: "#123456" } });
  vi.mocked(api.put).mockResolvedValue({ data: {} });
  fireEvent.click(screen.getByText("Save design"));
  await waitFor(() =>
    expect(api.put).toHaveBeenCalledWith("/plugins/appearance/", {
      settings: { ...defaults, primary: "#123456" },
      expected_revision: 0,
    }),
  );
});
