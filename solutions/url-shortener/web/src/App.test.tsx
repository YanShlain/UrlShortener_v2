import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const SHORT = "http://localhost:8080/aB3dE9x";

type FetchMock = ReturnType<typeof vi.fn>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(impl: (...args: unknown[]) => Promise<Response>): FetchMock {
  // v2: the page also loads GET /api/links; answer it with an empty list, route the rest to impl.
  const fn = vi.fn((...args: unknown[]) => {
    const init = args[1] as RequestInit | undefined;
    if (args[0] === "/api/links" && (init?.method ?? "GET") === "GET") {
      return Promise.resolve(jsonResponse(200, []));
    }
    return impl(...args);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function setClipboard(value: unknown): void {
  Object.defineProperty(navigator, "clipboard", { value, configurable: true });
}

function submitButton(container: HTMLElement): HTMLButtonElement {
  const b = container.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (!b) throw new Error("no submit button");
  return b;
}

function submit(container: HTMLElement, url: string): void {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: url } });
  fireEvent.click(submitButton(container));
}

beforeEach(() => {
  setClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("URL shortener UI", () => {
  it("shows the short URL as text with a Copy button on success", async () => {
    const fetchMock = mockFetch(() =>
      Promise.resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })),
    );
    const { container } = render(<App />);
    submit(container, "https://example.com/docs");
    expect(await screen.findByText(SHORT)).toBeTruthy();
    expect(screen.getByRole("button", { name: /copy/i })).toBeTruthy();
    const [url, init] = fetchMock.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === "POST",
    ) as [string, RequestInit];
    expect(url).toBe("/api/links");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ url: "https://example.com/docs" });
  });

  it("shows a loading state while the request is pending", async () => {
    let resolve: (r: Response) => void = () => undefined;
    mockFetch(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    );
    const { container } = render(<App />);
    submit(container, "https://example.com/");
    await waitFor(() => expect(submitButton(container).disabled).toBe(true));
    expect(screen.queryByText(SHORT)).toBeNull();
    resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT }));
    expect(await screen.findByText(SHORT)).toBeTruthy();
    expect(submitButton(container).disabled).toBe(false);
  });

  it("Copy writes the short URL to the clipboard and shows Copied", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    mockFetch(() => Promise.resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })));
    const { container } = render(<App />);
    submit(container, "https://example.com/");
    fireEvent.click(await screen.findByRole("button", { name: /copy/i }));
    expect(await screen.findByText(/copied/i)).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith(SHORT);
  });

  it("shows the server message on 422 and no short URL", async () => {
    mockFetch(() =>
      Promise.resolve(jsonResponse(422, { detail: "URL must start with http:// or https://" })),
    );
    const { container } = render(<App />);
    submit(container, "ftp://a.com");
    expect(await screen.findByText("URL must start with http:// or https://")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
    expect(submitButton(container).disabled).toBe(false);
  });

  it("shows an error on 500 and clears the previous short URL", async () => {
    let n = 0;
    mockFetch(() => {
      n += 1;
      return Promise.resolve(
        n === 1
          ? jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })
          : jsonResponse(500, { detail: "Internal error" }),
      );
    });
    const { container } = render(<App />);
    submit(container, "https://example.com/1");
    await screen.findByText(SHORT);
    submit(container, "https://example.com/2");
    expect(await screen.findByText(/internal error/i)).toBeTruthy();
    expect(screen.queryByText(SHORT)).toBeNull();
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });

  it("shows an error on network failure and stays usable", async () => {
    mockFetch(() => Promise.reject(new TypeError("Failed to fetch")));
    const { container } = render(<App />);
    submit(container, "https://example.com/");
    expect(await screen.findByText(/error|failed|network|try again|could not/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
    expect(submitButton(container).disabled).toBe(false);
  });

  it("does not call the api for an empty input (client-side validation)", async () => {
    const fetchMock = mockFetch(() => Promise.resolve(jsonResponse(201, {})));
    const { container } = render(<App />);
    fireEvent.click(submitButton(container));
    await waitFor(() => expect(screen.queryByRole("button", { name: /copy/i })).toBeNull());
    expect(
      fetchMock.mock.calls.filter((c) => (c[1] as RequestInit | undefined)?.method === "POST"),
    ).toHaveLength(0);
  });

  it("shows an error when the clipboard API is missing and not Copied", async () => {
    setClipboard(undefined);
    mockFetch(() => Promise.resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })));
    const { container } = render(<App />);
    submit(container, "https://example.com/");
    fireEvent.click(await screen.findByRole("button", { name: /copy/i }));
    expect(await screen.findByText(/copy|clipboard|unable|failed|error/i)).toBeTruthy();
    expect(screen.queryByText(/^copied$/i)).toBeNull();
    expect(screen.getByRole("button", { name: /copy/i })).toBeTruthy();
  });

  it("shows an error when the clipboard rejects", async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error("denied")) });
    mockFetch(() => Promise.resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })));
    const { container } = render(<App />);
    submit(container, "https://example.com/");
    fireEvent.click(await screen.findByRole("button", { name: /copy/i }));
    expect(await screen.findByText(/could not|unable|failed|denied|error/i)).toBeTruthy();
    expect(screen.queryByText(/^copied$/i)).toBeNull();
  });

  it("renders HTML in server messages and URLs as text, never as markup", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    mockFetch(() => Promise.resolve(jsonResponse(422, { detail: evil })));
    const { container } = render(<App />);
    submit(container, "http://a.com/<script>alert(1)</script>");
    expect(await screen.findByText(evil)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("does not turn a user-supplied URL into a link href", async () => {
    mockFetch(() => Promise.resolve(jsonResponse(201, { code: "aB3dE9x", short_url: SHORT })));
    const { container } = render(<App />);
    submit(container, "javascript:alert(1)");
    await screen.findByText(SHORT);
    for (const a of Array.from(container.querySelectorAll("a"))) {
      expect(a.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
    }
  });
});
