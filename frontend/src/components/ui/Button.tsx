import type { ButtonHTMLAttributes } from "react";

const looks = {
  primary: "bg-ink text-surface hover:opacity-90",
  secondary: "border bg-surface text-ink hover:bg-raised",
  text: "text-accent hover:underline",
} as const;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { look?: keyof typeof looks };

export function Button({ look = "primary", className = "", ...rest }: Props) {
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex h-control min-w-touch items-center justify-center rounded-control px-3 text-body font-medium disabled:opacity-50 max-md:h-touch ${looks[look]} ${className}`}
    />
  );
}
