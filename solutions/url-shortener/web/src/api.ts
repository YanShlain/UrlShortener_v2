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

export interface LinkItem {
  code: string;
  short_url: string;
  url: string;
  created_at: string;
}

function isLinkItem(v: unknown): v is LinkItem {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.code === "string" &&
    typeof o.short_url === "string" &&
    typeof o.url === "string" &&
    typeof o.created_at === "string"
  );
}

export async function listLinks(): Promise<LinkItem[]> {
  let res: Response;
  try {
    res = await fetch("/api/links");
  } catch {
    throw new Error("Network error: could not reach the server. Try again.");
  }
  if (!res.ok) throw new Error(await errorMessage(res));
  const body: unknown = await res.json().catch(() => null);
  if (Array.isArray(body) && body.every(isLinkItem)) return body;
  throw new Error("Unexpected response from the server.");
}
