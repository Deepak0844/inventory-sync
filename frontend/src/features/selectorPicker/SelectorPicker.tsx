import { useEffect, useRef, useState } from "react";

import type { TestRunSnapshot } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Icon } from "../../components/shell/Icon";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { resolveSelector } from "./resolve";
import { useSnapshotHtmlQuery } from "./snapshotApi";
import { stableSelector } from "./stableSelector";

const HOVER_ATTR = "data-picker-hover";
const PICKED_ATTR = "data-picker-picked";
const DEFAULT_HINT = "Click an element on the page to pick it.";
const NO_TARGET = "Press Pick next to a field first, then click the element.";

interface Props {
  snapshot: TestRunSnapshot;
  /** Called with the chosen selector, from a click on the page or from the typed field. */
  onPick: (selector: string) => void;
  /** Skip text selectors, for the stock element whose text changes. */
  avoidText?: boolean;
  /**
   * Where a click will go, for example "Fill step, Selector". A string names the target, null says
   * there is none yet (press Pick on a field), and leaving it out shows no target line at all.
   */
  targetLabel?: string | null;
}

/** The frame is a separate document, so its colours are read from the tokens and written in. */
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "currentColor";
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
export function SelectorPicker({ snapshot, onPick, avoidText = false, targetLabel }: Props) {
  const { data: html, isLoading, isError, refetch } = useSnapshotHtmlQuery(snapshot.html_url);
  const [view, setView] = useState<"page" | "screenshot">("page");
  const [hover, setHover] = useState<string | null>(null);
  // The target is kept with the pick, because it changes once the pick has been used.
  const [picked, setPicked] = useState<{ selector: string; label: string | null | undefined } | null>(null);
  const [typed, setTyped] = useState("");
  const [frameDoc, setFrameDoc] = useState<Document | null>(null);
  const detach = useRef<(() => void) | null>(null);
  // Listeners live as long as the frame, so they read the latest props from a ref.
  const latest = useRef({ onPick, avoidText, targetLabel });
  useEffect(() => {
    latest.current = { onPick, avoidText, targetLabel };
  });
  useEffect(() => () => detach.current?.(), []);

  const attach = (frame: HTMLIFrameElement) => {
    const doc = frame.contentDocument;
    if (!doc?.head) return;
    detach.current?.();
    setFrameDoc(doc);
    const style = doc.createElement("style");
    // The pick is drawn differently from the hover: heavier, in the positive colour, tinted.
    style.textContent =
      `[${HOVER_ATTR}]{outline:2px solid ${token("--accent")};outline-offset:1px;cursor:pointer}` +
      `[${PICKED_ATTR}]{outline:3px solid ${token("--positive")};outline-offset:2px;` +
      `background-color:${token("--pill-positive-bg")}}`;
    doc.head.append(style);

    let hovered: Element | null = null;
    let pickedEl: Element | null = null;
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
      setHover(`Click to pick ${stableSelector(el, { avoidText: latest.current.avoidText })}`);
    };
    const leave = () => {
      clear();
      setHover(null);
    };
    const click = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
      const el = event.target as Element;
      clear();
      const selector = stableSelector(el, { avoidText: latest.current.avoidText });
      pickedEl?.removeAttribute(PICKED_ATTR);
      el.setAttribute(PICKED_ATTR, "");
      pickedEl = el;
      setHover(null);
      setPicked({ selector, label: latest.current.targetLabel });
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
    setPicked({ selector, label: targetLabel });
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
          {targetLabel === undefined ? null : (
            <p className="text-small font-semibold text-ink">
              {targetLabel === null ? NO_TARGET : `Your next click fills: ${targetLabel}`}
            </p>
          )}
          {picked ? (
            <p role="status" className="text-small font-semibold text-positive">
              <Picked pick={picked} />
            </p>
          ) : null}
          <p className="text-small text-muted">{hover ?? DEFAULT_HINT}</p>
          <iframe
            title="Page snapshot"
            sandbox="allow-same-origin"
            srcDoc={html}
            referrerPolicy="no-referrer"
            onLoad={(event) => attach(event.currentTarget)}
            className="aspect-square w-full rounded-control border bg-surface"
          />
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
    </div>
  );
}

/** "(check) Picked #email for Fill step, Selector", shown above the page where it cannot be missed. */
function Picked({ pick }: { pick: { selector: string; label: string | null | undefined } }) {
  return (
    <>
      <span className="mr-1 inline-flex align-middle"><Icon name="approvals" /></span>Picked <span className="font-mono">{pick.selector}</span>
      {pick.label ? ` for ${pick.label}` : null}
    </>
  );
}
