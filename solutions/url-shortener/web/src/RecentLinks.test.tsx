import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

interface Item {
  code: string;
  short_url: string;
  url: string;
  created_at: string;
}

function item(n: number, url = `https://example.com/page/${n}`): Item {
  const code = `code${String(n).padStart(3, "0")}`;
  return {
    code,
    short_url: `http://localhost:8080/${code}`,
    url,
    created_at: "2026-11-27T10:15:00Z",
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (method: string) => Promise<Response>;

/** Routes GET /api/links to `list`, POST /api/links to `create`. Returns call recorders. */
function mockApi(list: Handler, create: Handler = () => Promise.resolve(jsonResponse(500, {}))) {
  const calls: { method: string; url: string }[] = [];
  const fn = vi.fn((...args: unknown[]) => {
    const url = String(args[0]);
    const method = ((args[1] as RequestInit | undefined)?.method ?? "GET").toUpperCase();
    calls.push({ method, url });
    return url === "/api/links" && method === "GET" ? list(method) : create(method);
  });
  vi.stubGlobal("fetch", fn);
  return {
    gets: () => calls.filter((c) => c.method === "GET" && c.url === "/api/links").length,
  };
}

function submit(container: HTMLElement, url: string): void {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: url } });
  const b = container.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (!b) throw new Error("no submit button");
  fireEvent.click(b);
}

function rows(): HTMLElement[] {
  const list = screen.queryByRole("list");
  return list ? within(list).queryAllByRole("listitem") : [];
}

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Recent links", () => {
  it("shows a loading state, then the rows newest first with safe anchors and full URL text", async () => {
    let resolve: (r: Response) => void = () => undefined;
    mockApi(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: /recent links/i })).toBeTruthy();
    expect(screen.getByText(/loading/i)).toBeTruthy();
    expect(rows()).toHaveLength(0);

    resolve(jsonResponse(200, [item(2), item(1)]));
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(screen.queryByText(/loading/i)).toBeNull();

    const [first, second] = rows();
    expect(first.textContent).toContain(item(2).url);
    expect(second.textContent).toContain(item(1).url);
    const a = within(first).getByRole("link");
    expect(a.getAttribute("href")).toBe(item(2).short_url);
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    expect(a.textContent).toBe(item(2).short_url);
    // the full URL is plain text, not part of any anchor
    expect(within(first).getAllByRole("link")).toHaveLength(1);
    expect(within(first).getByText(item(2).url).closest("a")).toBeNull();
  });

  it("shows an empty state and no list items for an empty list", async () => {
    mockApi(() => Promise.resolve(jsonResponse(200, [])));
    render(<App />);
    expect(await screen.findByText(/no links yet/i)).toBeTruthy();
    expect(rows()).toHaveLength(0);
  });

  it("shows the privacy notice near the list (FM-22)", async () => {
    mockApi(() => Promise.resolve(jsonResponse(200, [])));
    render(<App />);
    expect(await screen.findByText(/visible to everyone/i)).toBeTruthy();
  });

  it("reloads the list after a successful create and shows the new link on top", async () => {
    let n = 0;
    const api = mockApi(
      () => {
        n += 1;
        return Promise.resolve(jsonResponse(200, n === 1 ? [item(1)] : [item(2), item(1)]));
      },
      () =>
        Promise.resolve(
          jsonResponse(201, { code: item(2).code, short_url: item(2).short_url }),
        ),
    );
    const { container } = render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(api.gets()).toBe(1);
    submit(container, item(2).url);
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(api.gets()).toBe(2);
    expect(rows()[0].textContent).toContain(item(2).url);
  });

  it("reloads the list after a 200 (existing link) create too", async () => {
    const api = mockApi(
      () => Promise.resolve(jsonResponse(200, [item(1)])),
      () =>
        Promise.resolve(
          jsonResponse(200, { code: item(1).code, short_url: item(1).short_url }),
        ),
    );
    const { container } = render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    submit(container, item(1).url);
    await waitFor(() => expect(api.gets()).toBe(2));
  });

  it("does not reload the list when the create fails", async () => {
    const api = mockApi(
      () => Promise.resolve(jsonResponse(200, [item(1)])),
      () => Promise.resolve(jsonResponse(422, { detail: "URL must start with http://" })),
    );
    const { container } = render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    submit(container, "ftp://a.com");
    expect(await screen.findByText("URL must start with http://")).toBeTruthy();
    expect(api.gets()).toBe(1);
  });

  it("shows an inline list error on 500 without breaking the form, then recovers after a create", async () => {
    let n = 0;
    mockApi(
      () => {
        n += 1;
        return Promise.resolve(
          n === 1 ? jsonResponse(500, { detail: "Internal error" }) : jsonResponse(200, [item(1)]),
        );
      },
      () =>
        Promise.resolve(
          jsonResponse(201, { code: item(1).code, short_url: item(1).short_url }),
        ),
    );
    const { container } = render(<App />);
    expect(await screen.findByText(/could not load recent links/i)).toBeTruthy();
    expect(rows()).toHaveLength(0);
    // the form error area is not used for the list failure
    expect(screen.queryByRole("alert")?.textContent ?? "").not.toMatch(/recent links/i);
    const submitBtn = container.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(submitBtn?.disabled).toBe(false);

    submit(container, item(1).url);
    expect(await screen.findByText(item(1).short_url, { selector: ".short" })).toBeTruthy();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(screen.queryByText(/could not load recent links/i)).toBeNull();
  });

  it("shows the list error on a network failure and on invalid JSON", async () => {
    mockApi(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<App />);
    expect(await screen.findByText(/could not load recent links/i)).toBeTruthy();
    cleanup();
    vi.unstubAllGlobals();
    mockApi(() => Promise.resolve(new Response("not json", { status: 200 })));
    render(<App />);
    expect(await screen.findByText(/could not load recent links/i)).toBeTruthy();
  });

  it("ignores a stale list response that arrives after a newer one (FM-20)", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    mockApi(
      () =>
        new Promise<Response>((r) => {
          resolvers.push(r);
        }),
      () =>
        Promise.resolve(
          jsonResponse(201, { code: item(2).code, short_url: item(2).short_url }),
        ),
    );
    const { container } = render(<App />);
    await waitFor(() => expect(resolvers).toHaveLength(1));
    submit(container, item(2).url);
    await waitFor(() => expect(resolvers).toHaveLength(2));
    // newer response first, then the stale (older) one
    resolvers[1](jsonResponse(200, [item(2), item(1)]));
    await waitFor(() => expect(rows()).toHaveLength(2));
    resolvers[0](jsonResponse(200, [item(1)]));
    await new Promise((r) => setTimeout(r, 20));
    expect(rows()).toHaveLength(2);
    expect(rows()[0].textContent).toContain(item(2).url);
  });

  it("renders hostile URLs as inert text and never builds an href from them (FM-17, FM-23)", async () => {
    const evil = item(1, 'http://a.com/"><script>alert(1)</script>');
    const js = item(2, "javascript:alert(1)");
    const img = item(3, "http://a.com/<img src=x onerror=alert(1)>");
    mockApi(() => Promise.resolve(jsonResponse(200, [img, js, evil])));
    const { container } = render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(evil.url)).toBeTruthy();
    expect(screen.getByText(js.url)).toBeTruthy();
    expect(screen.getByText(img.url)).toBeTruthy();
    const shorts = new Set([evil.short_url, js.short_url, img.short_url]);
    const anchors = Array.from(container.querySelectorAll("a"));
    expect(anchors).toHaveLength(3);
    for (const a of anchors) {
      expect(shorts.has(a.getAttribute("href") ?? "")).toBe(true);
    }
  });

  it("keeps a 2048-character URL fully in the DOM (FM-23)", async () => {
    const long = "http://long.example/" + "a".repeat(2048 - "http://long.example/".length);
    mockApi(() => Promise.resolve(jsonResponse(200, [item(1, long)])));
    render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(rows()[0].textContent).toContain(long);
  });

  it("every anchor has target=_blank and rel=noopener noreferrer (FM-21)", async () => {
    mockApi(() => Promise.resolve(jsonResponse(200, [item(3), item(2), item(1)])));
    const { container } = render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(3));
    const anchors = Array.from(container.querySelectorAll("a"));
    expect(anchors).toHaveLength(3);
    for (const a of anchors) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });
});
