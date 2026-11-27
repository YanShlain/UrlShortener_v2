export interface ShortLink {
  code: string;
  short_url: string;
}

export const MAX_URL_LENGTH = 2048;

/** Mirrors the server's trim and length rules; the server stays the authority. */
export function validateUrl(raw: string): string | null {
  const url = raw.trim();
  if (url.length === 0) return "Enter a URL.";
  if (url.length > MAX_URL_LENGTH) return `URL must be at most ${MAX_URL_LENGTH} characters.`;
  return null;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string" && detail) return detail;
    }
  } catch {
    // fall through to the generic message
  }
  return `Request failed (${res.status}). Please try again.`;
}

export async function createLink(url: string): Promise<ShortLink> {
  let res: Response;
  try {
    res = await fetch("/api/links", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    });
  } catch {
    throw new Error("Network error: could not reach the server. Try again.");
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  const body: unknown = await res.json().catch(() => null);
  if (
    typeof body === "object" &&
    body !== null &&
    typeof (body as ShortLink).short_url === "string" &&
    typeof (body as ShortLink).code === "string"
  ) {
    return body as ShortLink;
  }
  throw new Error("Unexpected response from the server.");
}
