import { useId, type SelectHTMLAttributes } from "react";

type Props = SelectHTMLAttributes<HTMLSelectElement> & { label: string };

/** Labelled native select, styled like TextField. */
export function SelectField({ label, className = "", children, ...rest }: Props) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-small font-medium text-muted">{label}</label>
      <select
        id={id}
        {...rest}
        className={`h-control rounded-control border border-control bg-surface px-3 text-body max-md:h-touch ${className}`}
      >
        {children}
      </select>
    </div>
  );
}
