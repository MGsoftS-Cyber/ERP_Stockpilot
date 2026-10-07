// Teaching edition: Translate the backend error envelope into a readable message.
import axios from "axios";

interface ApiErrorEnvelope {
  error?: {
    detail?: unknown;
  };
}

function flatten(detail: unknown, prefix = ""): string[] {
  if (Array.isArray(detail))
    return detail.flatMap((item, index) =>
      flatten(item, typeof item === "object" && item !== null ? `${prefix}[${index}]` : prefix),
    );
  if (detail && typeof detail === "object")
    return Object.entries(detail).flatMap(([field, value]) =>
      flatten(value, prefix ? `${prefix}.${field}` : field),
    );
  return [prefix ? `${prefix}: ${String(detail)}` : String(detail)];
}

export function getApiErrorMessage(error: unknown): string {
  if (!axios.isAxiosError<ApiErrorEnvelope>(error)) {
    return error instanceof Error ? error.message : "An unexpected error occurred.";
  }

  const detail = error.response?.data?.error?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    return flatten(detail).join(" | ");
  }
  return error.message;
}
