import { forwardRef, useId, type InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string };

/** Labelled input that works with React Hook Form's `register`. */
export const TextField = forwardRef<HTMLInputElement, Props>(function TextField(
  { label, error, className = "", ...rest },
  ref,
) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-small font-medium text-muted">{label}</label>
      <input
        id={id}
        ref={ref}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...rest}
        className={`h-control rounded-control border border-control bg-surface px-3 text-body max-md:h-touch ${className}`}
      />
      {error ? <p id={`${id}-error`} className="text-small text-negative">{error}</p> : null}
    </div>
  );
});
