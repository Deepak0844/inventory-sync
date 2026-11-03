const paths = {
  overview: "M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z",
  suppliers: "M2 6l6-4 6 4v7H2zM6 13V9h4v4",
  listings: "M2 3h12M2 8h12M2 13h12",
  variants: "M8 2l6 3v6l-6 3-6-3V5zM2 5l6 3 6-3M8 8v6",
  approvals: "M3 8l3 3 7-7",
  orders: "M2 3h2l1.5 7h7L14 5H5M6 13.5h.01M12 13.5h.01",
  flows: "M3 3h4v3H3zM9 10h4v3H9zM5 6v2.5h6V10",
  settings: "M2 5h8M12 5h2M2 11h2M6 11h8M10 3v4M4 9v4",
  menu: "M2 4h12M2 8h12M2 12h12",
  close: "M3 3l10 10M13 3L3 13",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-icon w-icon shrink-0 fill-none stroke-current" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d={paths[name]} />
    </svg>
  );
}
