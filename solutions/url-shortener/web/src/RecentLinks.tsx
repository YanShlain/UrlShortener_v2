import type { LinkItem } from "./api";

export type ListState =
  | { state: "loading" }
  | { state: "ok"; items: LinkItem[] }
  | { state: "error" };

export default function RecentLinks({ list }: { list: ListState }) {
  return (
    <section className="recent">
      <h2>Recent links</h2>
      <p className="notice">Recent links are visible to everyone.</p>
      {list.state === "loading" && <p>Loading...</p>}
      {list.state === "error" && <p className="error">Could not load recent links.</p>}
      {list.state === "ok" && list.items.length === 0 && <p>No links yet.</p>}
      {list.state === "ok" && list.items.length > 0 && (
        <ul>
          {list.items.map((it) => (
            <li key={it.code}>
              <a href={it.short_url} target="_blank" rel="noopener noreferrer">
                {it.short_url}
              </a>
              <span className="full">{it.url}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
