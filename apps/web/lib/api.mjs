export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export async function requestJson(path, init, fetcher = fetch) {
  let response;

  try {
    response = await fetcher(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new Error(
      `Cannot reach the local API at ${API_BASE_URL}. Start FastAPI and try again.`,
      { cause: error },
    );
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.message ?? data?.detail?.message ?? data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `The local API returned HTTP ${response.status}.`,
    );
  }

  return data;
}

export function errorMessage(error) {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
