import { ReactFlowProvider } from "@xyflow/react";
import { useEffect, useMemo, useReducer, useRef, useState, type ComponentType } from "react";
import { useNavigate } from "react-router-dom";

import { useFlowQuery, useSetFlowMutation, useSupplierQuery } from "../../api/api";
import type { FlowDefinition, Supplier } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { flowErrors } from "../suppliers/flowErrors";
import { applyChange, draftFromFlow, draftToFlow } from "./builderState";
import { ROW } from "./convert";
import { FlowCanvas } from "./FlowCanvas";
import { starterFlow, toFlowDoc } from "./flowDoc";
import { Inspector } from "./Inspector";
import { Palette } from "./Palette";
import { SelectorColumn, type SelectorColumnProps } from "./SelectorColumn";
import { pickTarget } from "./nodeInfo";
import { PickFlashContext } from "./pickFlash";
import type { FlowDoc, NodeType, Validation } from "./types";
import { useIsPhone } from "./useIsPhone";
import { attachServerErrors, validateFlow } from "./validate";

const plural = (n: number) => (n === 1 ? "1 problem" : `${n} problems`);

interface EditorProps {
  supplier: Supplier;
  initial: FlowDoc;
  startsNew: boolean;
  SelectorPanel: ComponentType<SelectorColumnProps>;
}

/** The selector field of each step type that has exactly one. */
/** How long a field that was just filled by a pick stays flagged. */
const FLASH_MS = 2000;

const ONLY_SELECTOR_FIELD: Partial<Record<NodeType, string>> = {
  fill: "selector",
  click: "selector",
  wait_for: "selector",
  branch: "if_visible",
};

function Editor({ supplier, initial, startsNew, SelectorPanel }: EditorProps) {
  const navigate = useNavigate();
  const phone = useIsPhone();
  const [save, { isLoading: saving }] = useSetFlowMutation();
  const [draft, dispatch] = useReducer(applyChange, initial, draftFromFlow);
  // Compared as JSON, so the baseline goes through the same conversion as the draft (key order).
  const [baseline, setBaseline] = useState(() => draftToFlow(draftFromFlow(initial)));
  const [isNew, setIsNew] = useState(startsNew);
  const [savedJson, setSavedJson] = useState<string | null>(null);
  const [server, setServer] = useState<{ json: string; found: Validation } | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [pick, setPick] = useState<{ nodeId: string | null; field: string } | null>(null);
  const [formVersion, setFormVersion] = useState(0);
  const [pickNote, setPickNote] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const flow = useMemo(() => draftToFlow(draft), [draft]);
  const json = JSON.stringify(flow);
  const edited = json !== JSON.stringify(baseline);
  const local = useMemo(() => validateFlow(flow), [flow]);
  const refused = server?.json === json ? server.found : null;

  const selected = draft.graph.nodes.find((n) => n.selected)?.data.node ?? null;
  const picking = pick && pick.nodeId === (selected?.id ?? null) ? pick.field : null;

  const problems: Record<string, string[]> = { ...local.nodes };
  for (const [id, list] of Object.entries(refused?.nodes ?? {})) problems[id] = [...(problems[id] ?? []), ...list];
  const flowMessages = [...local.flow, ...(refused?.flow ?? [])];
  const problemCount = flowMessages.length + Object.keys(problems).length;

  useEffect(() => {
    if (!edited) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [edited]);

  const lowest = draft.graph.nodes.reduce((a, n) => (n.position.y >= a.position.y ? n : a), draft.graph.nodes[0]);
  const add = (type: NodeType) =>
    dispatch({
      kind: "add",
      nodeType: type,
      position: lowest ? { x: lowest.position.x, y: lowest.position.y + ROW } : { x: 0, y: 0 },
      after: selected?.id ?? flow.nodes.at(-1)?.id,
    });

  const onSave = async () => {
    try {
      await save({ id: supplier.id, flow: flow as unknown as FlowDefinition }).unwrap();
      setBaseline(flow);
      setIsNew(false);
      setSavedJson(json);
      setServer(null);
    } catch (error) {
      setServer({ json, found: attachServerErrors(flowErrors(error), flow.nodes.map((n) => n.id)) });
    }
  };
  const revert = () => {
    dispatch({ kind: "replace", flow: baseline });
    setServer(null);
    setPick(null);
    setFormVersion((v) => v + 1);
  };
  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flash]);

  const onPickSelector = (selector: string) => {
    // A step with one selector field is the obvious target, so it needs no Pick press first.
    const field = picking ?? (selected ? ONLY_SELECTOR_FIELD[selected.type] : undefined);
    if (!field) {
      setPickNote("Press Pick next to a field first, then click the element.");
      return;
    }
    if (selected) dispatch({ kind: "update", node: { ...selected, [field]: selector } as typeof selected });
    else dispatch({ kind: "extract", patch: { [field]: selector } });
    setPick(null);
    setPickNote(null);
    setFlash(field);
    setFormVersion((v) => v + 1);
  };

  const status = edited ? "Unsaved changes" : isNew ? "Not saved yet" : savedJson === json ? "Flow saved." : "";
  const canSave = (edited || isNew) && local.ok && !refused && !saving;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <Button look="text" onClick={() => (edited ? setLeaving(true) : navigate("/flows"))}>Back to flows</Button>
        <h1 className="text-title font-semibold">{supplier.name} flow</h1>
        {status ? <p role="status" className="text-small text-muted">{status}</p> : null}
        {pickNote ? <p role="status" className="text-small text-negative">{pickNote}</p> : null}
        {!phone ? (
          <div className="ml-auto flex items-center gap-2">
            {!local.ok ? <p className="text-small text-negative">Fix {plural(problemCount)} to save</p> : null}
            <Button look="secondary" onClick={revert} disabled={!edited}>Revert</Button>
            <Button onClick={() => void onSave()} disabled={!canSave}>Save</Button>
          </div>
        ) : null}
      </header>

      {leaving ? (
        <div role="alertdialog" aria-label="Leave without saving?" className="flex flex-wrap items-center gap-3 rounded-card border bg-raised p-3">
          <p className="text-body">Leave without saving?</p>
          <Button look="secondary" onClick={() => setLeaving(false)}>Stay</Button>
          <Button onClick={() => navigate("/flows")}>Leave</Button>
        </div>
      ) : null}
      {isNew ? <p className="text-body text-muted">No flow yet. This is a starting outline for a login: pick the selectors, then save.</p> : null}
      {phone ? <p className="text-body text-muted">The builder is read-only on a phone. Open it on a larger screen to edit.</p> : null}
      {flowMessages.length > 0 ? (
        <ul role="alert" className="flex flex-col gap-1 text-small text-negative">
          {flowMessages.map((m) => <li key={m}>{m}</li>)}
        </ul>
      ) : null}

      <div className="grid gap-4 md:grid-cols-[theme(spacing.sidebar)_minmax(0,1fr)_calc(theme(spacing.sidebar)*1.5)]">
        {!phone ? <aside><Card title="Add a step"><Palette onAdd={add} /></Card></aside> : null}
        <div className="h-[calc(100dvh-theme(spacing.topbar)-theme(spacing.8)*5)] min-h-reading overflow-hidden rounded-card border">
          <ReactFlowProvider>
            <FlowCanvas
              draft={draft}
              problems={problems}
              readOnly={phone}
              onChange={dispatch}
              onAdd={(type, position) => dispatch({ kind: "add", nodeType: type, position })}
            />
          </ReactFlowProvider>
        </div>
        {!phone ? (
          <aside className="flex flex-col gap-4">
            <Card>
              <PickFlashContext.Provider value={flash}>
              <Inspector
                selected={selected}
                meta={draft.meta}
                onNode={(node) => dispatch({ kind: "update", node })}
                onMeta={(patch) => dispatch({ kind: "meta", patch })}
                onExtract={(patch) => dispatch({ kind: "extract", patch })}
                onPick={(field) => setPick(picking === field ? null : { nodeId: selected?.id ?? null, field })}
                picking={picking}
                pickVersion={formVersion}
                readOnly={false}
              />
              </PickFlashContext.Provider>
              {selected ? (
                <div className="mt-3">
                  <Button look="text" onClick={() => dispatch({ kind: "remove", id: selected.id })}>Remove this step</Button>
                </div>
              ) : null}
            </Card>
            <Card title="Test run">
              <p className="mb-2 text-small text-muted">Test runs never write to Shopify.</p>
              <SelectorPanel
                supplierId={supplier.id}
                getDraftFlow={() => flow as unknown as FlowDefinition}
                selectedNodeId={selected?.id ?? null}
                onPickSelector={onPickSelector}
                targetLabel={pickTarget(selected, picking ?? (selected ? ONLY_SELECTOR_FIELD[selected.type] : undefined))}
              />
            </Card>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

interface Props {
  supplierId: number;
  /** The Test run and selector picker column; the placeholder until the real one is wired in. */
  SelectorPanel?: ComponentType<SelectorColumnProps>;
}

/** Screen 8, the builder for one Supplier's flow: loads it, then hands over to the editor. */
export function FlowBuilder({ supplierId, SelectorPanel = SelectorColumn }: Props) {
  // RTK Query reuses a cached result for 60 s after a screen is left, so a flow changed or deleted
  // meanwhile would still show. Ask again on every open, and wait for that answer once, so a later
  // refetch (after Save) does not replace the editor and lose what is being edited.
  const flowQuery = useFlowQuery(supplierId, { refetchOnMountOrArgChange: true });
  const supplierQuery = useSupplierQuery(supplierId);
  const openedAt = useRef(Date.now());
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    // Fresh means the answer comes from a request that started after this screen opened.
    const started = flowQuery.startedTimeStamp;
    if (!flowQuery.isFetching && started !== undefined && started >= openedAt.current) setFresh(true);
  }, [flowQuery.isFetching, flowQuery.startedTimeStamp]);
  const noFlowYet = (flowQuery.error as { status?: number } | undefined)?.status === 404;

  if (!fresh || flowQuery.isLoading || supplierQuery.isLoading) return <BlockState kind="loading" />;
  if ((flowQuery.isError && !noFlowYet) || supplierQuery.isError || !supplierQuery.data) {
    return (
      <BlockState
        kind="error"
        message="Couldn't load the flow."
        onRetry={() => {
          void flowQuery.refetch();
          void supplierQuery.refetch();
        }}
      />
    );
  }
  // After a 404 RTK Query still holds the last good result as `data`; the answer now is "no flow".
  const saved = noFlowYet ? undefined : flowQuery.data;
  const initial = saved ? toFlowDoc(saved) : starterFlow(supplierQuery.data);
  return <Editor key={supplierId} supplier={supplierQuery.data} initial={initial} startsNew={!saved} SelectorPanel={SelectorPanel} />;
}
