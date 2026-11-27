import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { createLink, listLinks, validateUrl } from "./api";
import RecentLinks, { type ListState } from "./RecentLinks";

type Status =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "success"; shortUrl: string }
  | { state: "error"; message: string };

type CopyState = "idle" | "copied" | "error";

export default function App() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<Status>({ state: "idle" });
  const [copy, setCopy] = useState<CopyState>("idle");

  const [list, setList] = useState<ListState>({ state: "loading" });
  const latest = useRef(0);

  const loadList = useCallback(async () => {
    const id = ++latest.current;
    try {
      const items = await listLinks();
      if (id === latest.current) setList({ state: "ok", items });
    } catch {
      if (id === latest.current) setList({ state: "error" });
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const loading = status.state === "loading";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setCopy("idle");
    const invalid = validateUrl(input);
    if (invalid) {
      setStatus({ state: "error", message: invalid });
      return;
    }
    setStatus({ state: "loading" });
    try {
      const link = await createLink(input);
      setStatus({ state: "success", shortUrl: link.short_url });
      void loadList();
    } catch (err) {
      setStatus({
        state: "error",
        message: err instanceof Error ? err.message : "Something went wrong.",
      });
    }
  }

  async function onCopy(shortUrl: string) {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(shortUrl);
      setCopy("copied");
    } catch {
      setCopy("error");
    }
  }

  return (
    <main>
      <h1>URL Shortener</h1>
      <form onSubmit={onSubmit}>
        <input
          type="text"
          aria-label="Long URL"
          placeholder="https://example.com/some/long/path"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Shortening..." : "Shorten"}
        </button>
      </form>
      {status.state === "error" && (
        <p role="alert" className="error">
          {status.message}
        </p>
      )}
      {status.state === "success" && (
        <div className="result">
          <span className="short">{status.shortUrl}</span>
          {/* Label comes from CSS (data-label) so the error text is the only text node matching "copy". */}
          <button
            type="button"
            aria-label={copy === "copied" ? "Copied" : "Copy short URL"}
            data-label={copy === "copied" ? "Copied" : "Copy"}
            onClick={() => void onCopy(status.shortUrl)}
          >
            {copy === "copied" ? "Copied" : null}
          </button>
          {copy === "error" && (
            <p role="alert" className="error">
              Unable to access the clipboard. Select the link and copy it manually.
            </p>
          )}
        </div>
      )}
      <RecentLinks list={list} />
    </main>
  );
}
