import { api } from "./client";
import type { PaginatedResponse } from "../types";
// Dropdowns need every choice, not just the API's first page. Never follow an arbitrary next URL.
export async function allPages<T>(endpoint: string): Promise<PaginatedResponse<T>> {
  const results: T[] = [];
  for (let page = 1; ; page++) {
    const { data } = await api.get<PaginatedResponse<T>>(endpoint, { params: { page } });
    results.push(...data.results);
    if (!data.next) return { results, count: results.length, next: null, previous: null };
  }
}
