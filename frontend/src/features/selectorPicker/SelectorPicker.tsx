import { useEffect, useRef, useState } from "react";

import type { TestRunSnapshot } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { resolveSelector } from "./resolve";
import { useSnapshotHtmlQuery } from "./snapshotApi";
import { stableSelector } from "./stableSelector";

const HOVER_ATTR = "data-picker-hover";
const DEFAULT_HINT = "Click an element on the page to pick it.";

interface Props {
  snapshot: TestRunSnapshot;
  /** Called with the chosen selector, from a click on the page or from the typed field. */
  onPick: (selector: string) => void;
  /** Skip text selectors, for the stock element whose text changes. */
  avoidText?: boolean;
}

/** The highlight colour comes from the accent token, because the frame is a separate document. */
function accentColour(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "currentColor";
}

function describeMatches(doc: Document | null, selector: string): string | null {
  const wanted = selector.trim();
  if (!doc || !wanted) return null;
  try {
    const n = resolveSelector(doc, wanted).length;
    if (n === 0) return "Matches nothing on this page.";
    return `Matches ${n} ${n === 1 ? "element" : "elements"} on this page.`;
  } catch {
    return "That isn't a valid selector.";
  }
}

/**
 * Shows the cleaned page snapshot of a Test run so a flow author can click the element they mean.
 * The page is rendered in a sandboxed frame without scripts; the parent attaches the hover and
 * click listeners, so nothing from the Supplier's page runs.
 */
export function SelectorPicker({ snapshot, onPick, avoidText = false }: Props) {
  const { data: html, isLoading, isError, refetch } = useSnapshotHtmlQuery(snapshot.html_url);
  const [view, setView] = useState<"page" | "screenshot">("page");
  const [hint, setHint] = useState(DEFAULT_HINT);
  const [picked, setPicked] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [frameDoc, setFrameDoc] = useState<Document | null>(null);
  const detach = useRef<(() => void) | null>(null);
  // Listeners live as long as the frame, so they read the latest props from a ref.
  const latest = useRef({ onPick, avoidText });
  useEffect(() => {
    latest.current = { onPick, avoidText };
  });
  useEffect(() => () => detach.current?.(), []);

  const attach = (frame: HTMLIFrameElement) => {
    const doc = frame.contentDocument;
    if (!doc?.head) return;
    detach.current?.();
    setFrameDoc(doc);
    const style = doc.createElement("style");
    style.textContent = `[${HOVER_ATTR}]{outline:2px solid ${accentColour()};outline-offset:1px;cursor:pointer}`;
    doc.head.append(style);

    let hovered: Element | null = null;
    const clear = () => {
      hovered?.removeAttribute(HOVER_ATTR);
      hovered = null;
    };
    const over = (event: Event) => {
      const el = event.target as Element;
      if (el === hovered || el.localName === "html") return;
      clear();
      hovered = el;
      el.setAttribute(HOVER_ATTR, "");
      setHint(`Click to pick ${stableSelector(el, { avoidText: latest.current.avoidText })}`);
    };
    const leave = () => {
      clear();
      setHint(DEFAULT_HINT);
    };
    const click = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
      const el = event.target as Element;
      clear();
      const selector = stableSelector(el, { avoidText: latest.current.avoidText });
      setPicked(selector);
      latest.current.onPick(selector);
    };
    const block = (event: Event) => event.preventDefault();
    doc.addEventListener("mouseover", over);
    doc.documentElement.addEventListener("mouseleave", leave);
    doc.addEventListener("click", click, true);
    doc.addEventListener("submit", block, true);
    detach.current = () => {
      doc.removeEventListener("mouseover", over);
      doc.documentElement.removeEventListener("mouseleave", leave);
      doc.removeEventListener("click", click, true);
      doc.removeEventListener("submit", block, true);
    };
  };

  const show = (next: "page" | "screenshot") => {
    setView(next);
    setFrameDoc(null);
  };
  const matches = view === "page" ? describeMatches(frameDoc, typed) : null;
  const use = () => {
    const selector = typed.trim();
    setPicked(selector);
    onPick(selector);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2" role="group" aria-label="View">
        <Button look={view === "page" ? "secondary" : "text"} aria-pressed={view === "page"} onClick={() => show("page")}>
          Page
        </Button>
        <Button look={view === "screenshot" ? "secondary" : "text"} aria-pressed={view === "screenshot"} onClick={() => show("screenshot")}>
          Screenshot
        </Button>
      </div>

      {view === "screenshot" ? (
        <img src={snapshot.screenshot_url} alt="Screenshot of the page at this step" className="w-full rounded-control border" />
      ) : isLoading ? (
        <BlockState kind="loading" />
      ) : isError || html === undefined ? (
        <BlockState kind="error" message="Couldn't load the page snapshot." onRetry={() => void refetch()} />
      ) : (
        <>
          <iframe
            title="Page snapshot"
            sandbox="allow-same-origin"
            srcDoc={html}
            referrerPolicy="no-referrer"
            onLoad={(event) => attach(event.currentTarget)}
            className="aspect-square w-full rounded-control border bg-surface"
          />
          <p className="text-small text-muted">{hint}</p>
        </>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <TextField label="Or type a selector" value={typed} onChange={(e) => setTyped(e.target.value)} className="w-full font-mono" />
        </div>
        <Button look="secondary" disabled={typed.trim() === ""} onClick={use}>
          Use selector
        </Button>
      </div>
      {matches ? <p className="text-small text-muted">{matches}</p> : null}
      <p aria-live="polite" className="text-small text-muted">
        {picked ? <>Picked <span className="font-mono text-ink">{picked}</span></> : null}
      </p>
    </div>
  );
}
