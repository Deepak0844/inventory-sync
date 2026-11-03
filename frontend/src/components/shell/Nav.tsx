import { NavLink } from "react-router-dom";

import type { Banner } from "../../api/types";
import { Icon, type IconName } from "./Icon";

interface Item { to: string; label: string; icon: IconName; count?: number }

/** Counts appear only on queues that need action. */
export function navItems(counts: Banner["counts"] | undefined): { main: Item[]; build: Item[] } {
  const queue = (n: number | undefined) => (n && n > 0 ? n : undefined);
  return {
    main: [
      { to: "/", label: "Overview", icon: "overview" },
      { to: "/suppliers", label: "Suppliers", icon: "suppliers" },
      { to: "/listings", label: "Listings", icon: "listings" },
      { to: "/variants", label: "Variants", icon: "variants" },
      { to: "/approvals", label: "Approvals", icon: "approvals", count: queue(counts?.approvals) },
      { to: "/orders", label: "Orders", icon: "orders", count: queue(counts?.orders) },
      { to: "/notifications", label: "Notifications", icon: "overview", count: queue(counts?.notifications) },
    ],
    build: [
      { to: "/flows", label: "Flows", icon: "flows" },
      { to: "/settings", label: "Settings", icon: "settings" },
    ],
  };
}

export function Nav({ counts, onNavigate }: { counts?: Banner["counts"]; onNavigate?: () => void }) {
  const { main, build } = navItems(counts);
  const row = (i: Item) => (
    <NavLink
      key={i.to}
      to={i.to}
      end={i.to === "/"}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex h-control items-center gap-2 rounded-control px-3 text-body max-md:h-touch ${isActive ? "bg-active font-semibold" : "text-muted hover:bg-raised"}`
      }
    >
      <Icon name={i.icon} />
      <span className="flex-1">{i.label}</span>
      {i.count ? <span className="text-small">{i.count}</span> : null}
    </NavLink>
  );
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {main.map(row)}
      <p className="mt-4 px-3 text-small text-muted">Build</p>
      {build.map(row)}
    </nav>
  );
}
