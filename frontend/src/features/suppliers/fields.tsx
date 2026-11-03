import { forwardRef, useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

type CheckboxProps = InputHTMLAttributes<HTMLInputElement> & { label: string };

/** A labelled checkbox that works with React Hook Form's `register`. */
export const CheckboxField = forwardRef<HTMLInputElement, CheckboxProps>(function CheckboxField(
  { label, ...rest },
  ref,
) {
  const id = useId();
  return (
    <div className="flex min-h-control items-center gap-2 max-md:min-h-touch">
      <input id={id} ref={ref} type="checkbox" {...rest} className="h-4 w-4 accent-accent" />
      <label htmlFor={id} className="text-body">{label}</label>
    </div>
  );
});

type AreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string };

/** A labelled multi-line field. Monospace because it holds JSON. */
export function TextArea({ label, className = "", ...rest }: AreaProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-small font-medium text-muted">{label}</label>
      <textarea
        id={id}
        spellCheck={false}
        {...rest}
        className={`rounded-control border border-control bg-surface p-3 font-mono text-small ${className}`}
      />
    </div>
  );
}

/** One line of feedback under a form: green-free, role-correct, shown only when there is text. */
export function FormMessage({ kind, children }: { kind: "ok" | "error"; children: string }) {
  return (
    <p role={kind === "error" ? "alert" : "status"} className={`text-small ${kind === "error" ? "text-negative" : "text-muted"}`}>
      {children}
    </p>
  );
}
