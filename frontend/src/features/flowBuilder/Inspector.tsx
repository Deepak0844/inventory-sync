import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { TextField } from "../../components/ui/TextField";
import { SelectorField, useCommit } from "./formKit";
import { NODE_LABELS } from "./nodeInfo";
import {
  AwaitCodeForm, BranchForm, ClickForm, FillForm, GotoForm, SaveSessionForm, WaitForForm,
  type NodeFormProps,
} from "./NodeForms";
import type { ExtractRules, FlowMeta, FlowNode } from "./types";

interface Props {
  selected: FlowNode | null;
  meta: FlowMeta;
  onNode: (node: FlowNode) => void;
  onMeta: (patch: Partial<FlowMeta>) => void;
  onExtract: (patch: Partial<ExtractRules>) => void;
  /** Starts waiting for a selector from the page snapshot, for the named field. */
  onPick: (field: string) => void;
  /** The field that is waiting for a pick. */
  picking: string | null;
  /** Changes when a pick fills a field, so the open form shows the new value. */
  pickVersion: number;
  readOnly: boolean;
}

function NodeForm(props: NodeFormProps) {
  const { node } = props;
  switch (node.type) {
    case "goto": return <GotoForm {...props} node={node} />;
    case "fill": return <FillForm {...props} node={node} />;
    case "click": return <ClickForm {...props} node={node} />;
    case "wait_for": return <WaitForForm {...props} node={node} />;
    case "await_code": return <AwaitCodeForm {...props} node={node} />;
    case "branch": return <BranchForm {...props} node={node} />;
    case "save_session": return <SaveSessionForm />;
  }
}

const required = (message: string) => z.string().trim().min(1, message);

function FlowSettings({ meta, onMeta, onExtract, onPick, picking }: Omit<Props, "selected" | "pickVersion" | "readOnly">) {
  const schema = z.object({
    login_path: required("Enter the login page path."),
    logged_in_url: required("Enter a page that only shows when signed in."),
    blocked: required("Enter the text that appears on a block page."),
    stock_selector: required("Pick the stock element."),
    in_text: required("Enter the text that means In stock."),
    out_text: required("Enter the text that means Out of stock."),
    quantity_selector: z.string(),
  });
  const form = useForm({
    defaultValues: {
      login_path: meta.login_path,
      logged_in_url: meta.logged_in_url,
      blocked: meta.blocked_if.contains,
      stock_selector: meta.extract.stock_selector,
      in_text: meta.extract.in_stock_if.contains,
      out_text: meta.extract.out_of_stock_if.contains,
      quantity_selector: meta.extract.quantity_selector ?? "",
    },
    resolver: zodResolver(schema),
    mode: "onChange",
  });
  // Each edit reports only the field that changed, so a half-typed field elsewhere is untouched.
  useCommit(form, (v, name) => {
    const value = (name ? (v as Record<string, string>)[name] : "") ?? "";
    if (name === "login_path" || name === "logged_in_url") onMeta({ [name]: value });
    else if (name === "blocked") onMeta({ blocked_if: { contains: value } });
    else if (name === "stock_selector") onExtract({ stock_selector: value });
    else if (name === "in_text") onExtract({ in_stock_if: { contains: value } });
    else if (name === "out_text") onExtract({ out_of_stock_if: { contains: value } });
    else if (name === "quantity_selector") onExtract({ quantity_selector: value || null });
  });
  const { errors } = form.formState;
  return (
    <>
      <h2 className="text-section font-semibold">Flow settings</h2>
      <TextField label="Login page path" {...form.register("login_path")} error={errors.login_path?.message} />
      <TextField label="Signed-in page address" {...form.register("logged_in_url")} error={errors.logged_in_url?.message} />
      <TextField label="Text that means blocked" {...form.register("blocked")} error={errors.blocked?.message} />
      <h2 className="mt-4 text-section font-semibold">Stock rules</h2>
      <SelectorField label="Stock element" field="stock_selector" picking={picking} onPick={onPick}
        error={errors.stock_selector?.message} inputProps={form.register("stock_selector")} />
      <TextField label="Text that means In stock" {...form.register("in_text")} error={errors.in_text?.message} />
      <TextField label="Text that means Out of stock" {...form.register("out_text")} error={errors.out_text?.message} />
      <SelectorField label="Quantity element (optional)" field="quantity_selector" picking={picking} onPick={onPick}
        inputProps={form.register("quantity_selector")} />
    </>
  );
}

/** The right-hand form: the selected step's fields, or the flow settings when nothing is selected. */
export function Inspector({ selected, pickVersion, readOnly, ...rest }: Props) {
  return (
    <fieldset disabled={readOnly} className="flex flex-col gap-3">
      {selected ? (
        <>
          <h2 className="text-section font-semibold">{NODE_LABELS[selected.type]}</h2>
          <NodeForm key={`${selected.id}:${pickVersion}`} node={selected} onNode={rest.onNode}
            picking={rest.picking} onPick={rest.onPick} />
        </>
      ) : (
        <FlowSettings key={pickVersion} {...rest} />
      )}
    </fieldset>
  );
}
