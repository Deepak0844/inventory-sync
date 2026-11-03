import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, type UseFormReturn } from "react-hook-form";
import { z } from "zod";

import { SelectField } from "../listings/SelectField";
import { CheckboxField } from "../suppliers/fields";
import { TextField } from "../../components/ui/TextField";
import { SelectorField, useCommit } from "./formKit";
import type {
  AwaitCodeNode, BranchNode, ClickNode, FillNode, FlowNode, GotoNode, WaitForNode,
} from "./types";

export interface NodeFormProps<N extends FlowNode = FlowNode> {
  node: N;
  onNode: (node: FlowNode) => void;
  picking: string | null;
  onPick: (field: string) => void;
}

const text = (message: string) => z.string().trim().min(1, message);
const seconds = z.number({ invalid_type_error: "Enter a number of seconds." }).min(0, "It can't be negative.");
const number = (value: number | undefined) => (value === undefined || Number.isNaN(value) ? undefined : value);

function useNodeForm<V extends Record<string, unknown>>(
  schema: z.ZodType<V, z.ZodTypeDef, unknown>,
  defaults: V,
): UseFormReturn<V> {
  return useForm<V>({ defaultValues: defaults as never, resolver: zodResolver(schema) as never, mode: "onChange" });
}

export function GotoForm({ node, onNode }: NodeFormProps<GotoNode>) {
  const form = useNodeForm(z.object({ url: text("Enter the page address.") }), { url: node.url });
  useCommit(form, (v) => onNode({ ...node, url: v.url ?? "" }));
  return <TextField label="Page address" {...form.register("url")} error={form.formState.errors.url?.message} />;
}

export function FillForm({ node, onNode, picking, onPick }: NodeFormProps<FillNode>) {
  const schema = z.object({
    selector: text("Pick or enter a selector."),
    value: text("Enter the value to type."),
    mask: z.boolean(),
  });
  const form = useNodeForm(schema, { selector: node.selector, value: node.value, mask: node.mask ?? false });
  useCommit(form, (v) => onNode({ ...node, selector: v.selector ?? "", value: v.value ?? "", mask: v.mask ?? false }));
  const { errors } = form.formState;
  return (
    <>
      <SelectorField label="Selector" field="selector" picking={picking} onPick={onPick}
        error={errors.selector?.message} inputProps={form.register("selector")} />
      <TextField label="Value to type" {...form.register("value")} error={errors.value?.message} />
      <p className="text-small text-muted">Use {"{{credentials.username}}"}, {"{{credentials.password}}"} or {"{{code}}"}.</p>
      <CheckboxField label="Hide the value in screenshots" {...form.register("mask")} />
    </>
  );
}

export function ClickForm({ node, onNode, picking, onPick }: NodeFormProps<ClickNode>) {
  const form = useNodeForm(z.object({ selector: text("Pick or enter a selector.") }), { selector: node.selector });
  useCommit(form, (v) => onNode({ ...node, selector: v.selector ?? "" }));
  return (
    <SelectorField label="Selector" field="selector" picking={picking} onPick={onPick}
      error={form.formState.errors.selector?.message} inputProps={form.register("selector")} />
  );
}

const ROLES = [
  ["", "Nothing in particular"],
  ["code_prompt", "The code box"],
  ["logged_in_marker", "The logged-in marker"],
] as const;

export function WaitForForm({ node, onNode, picking, onPick }: NodeFormProps<WaitForNode>) {
  const schema = z.object({
    selector: text("Pick or enter a selector."),
    role: z.string(),
    timeout_s: seconds,
  });
  const form = useNodeForm(schema, { selector: node.selector, role: node.role ?? "", timeout_s: node.timeout_s ?? 5 });
  useCommit(form, (v) =>
    onNode({
      ...node,
      selector: v.selector ?? "",
      role: (v.role || null) as WaitForNode["role"],
      timeout_s: number(v.timeout_s),
    }),
  );
  const { errors } = form.formState;
  return (
    <>
      <SelectorField label="Selector" field="selector" picking={picking} onPick={onPick}
        error={errors.selector?.message} inputProps={form.register("selector")} />
      <SelectField label="What this waits for" {...form.register("role")}>
        {ROLES.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
      </SelectField>
      <TextField label="Wait up to (seconds)" type="number" {...form.register("timeout_s", { valueAsNumber: true })}
        error={errors.timeout_s?.message} />
    </>
  );
}

export function AwaitCodeForm({ node, onNode }: NodeFormProps<AwaitCodeNode>) {
  const schema = z.object({
    methods: z.array(z.enum(["ui_code", "email_code"])).min(1, "Choose at least one way to get the code."),
    sender: z.string(),
    pattern: z.string(),
    timeout_s: seconds,
  }).superRefine((v, ctx) => {
    if (!v.methods.includes("email_code")) return;
    if (!v.sender.trim()) ctx.addIssue({ code: "custom", path: ["sender"], message: "Enter who sends the code." });
    if (!v.pattern.trim()) ctx.addIssue({ code: "custom", path: ["pattern"], message: "Enter the pattern that finds the code." });
  });
  const form = useNodeForm(schema, {
    methods: node.methods,
    sender: node.email?.sender ?? "",
    pattern: node.email?.pattern ?? "",
    timeout_s: node.timeout_s ?? 600,
  });
  useCommit(form, (v) => {
    const sender = v.sender ?? "";
    const pattern = v.pattern ?? "";
    onNode({
      ...node,
      methods: (v.methods ?? []) as AwaitCodeNode["methods"],
      email: sender || pattern ? { sender, pattern } : null,
      timeout_s: number(v.timeout_s),
    });
  });
  const { errors } = form.formState;
  const byEmail = (form.watch("methods") ?? []).includes("email_code");
  return (
    <>
      <fieldset className="flex flex-col">
        <legend className="mb-1 text-small font-medium text-muted">Where the code comes from</legend>
        <CheckboxField label="Pasted in the dashboard" value="ui_code" {...form.register("methods")} />
        <CheckboxField label="Mailbox" value="email_code" {...form.register("methods")} />
        {errors.methods ? <p className="text-small text-negative">{errors.methods.message}</p> : null}
      </fieldset>
      {byEmail ? (
        <>
          <TextField label="Sender" {...form.register("sender")} error={errors.sender?.message} />
          <TextField label="Pattern" {...form.register("pattern")} error={errors.pattern?.message} />
        </>
      ) : null}
      <TextField label="Give up after (seconds)" type="number" {...form.register("timeout_s", { valueAsNumber: true })}
        error={errors.timeout_s?.message} />
    </>
  );
}

export function BranchForm({ node, onNode, picking, onPick }: NodeFormProps<BranchNode>) {
  const form = useNodeForm(z.object({ if_visible: text("Pick or enter a selector.") }), { if_visible: node.if_visible });
  useCommit(form, (v) => onNode({ ...node, if_visible: v.if_visible ?? "" }));
  return (
    <>
      <SelectorField label="Element to look for" field="if_visible" picking={picking} onPick={onPick}
        error={form.formState.errors.if_visible?.message} inputProps={form.register("if_visible")} />
      <p className="text-small text-muted">Connect the yes path for when it is on the page, the no path for when it isn't.</p>
    </>
  );
}

export function SaveSessionForm() {
  return <p className="text-small text-muted">A Save session step has nothing to set. It keeps the cookies so the next run can skip the login.</p>;
}
