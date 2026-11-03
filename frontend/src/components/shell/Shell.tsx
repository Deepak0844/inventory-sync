import { Suspense, useState, type FormEvent } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { useBannerQuery, useLogoutMutation } from "../../api/api";
import { clock } from "../../lib/format";
import { useAppDispatch, useAppSelector } from "../../state/hooks";
import { closeMenu, openMenu } from "../../state/uiSlice";
import { BlockState } from "../ui/BlockState";
import { Button } from "../ui/Button";
import { Sheet } from "../ui/Sheet";
import { Icon } from "./Icon";
import { Nav } from "./Nav";
import { NeedsCodePrompt } from "./NeedsCodePrompt";
import { RedStrip } from "./RedStrip";

const BANNER_POLL_MS = 30_000;

/** The Framed sheet: tinted frame with sidebar and top bar, the white sheet inset on the right and bottom. */
export function Shell() {
  const { data: banner, fulfilledTimeStamp } = useBannerQuery(undefined, { pollingInterval: BANNER_POLL_MS });
  const [logout] = useLogoutMutation();
  const menuOpen = useAppSelector((s) => s.ui.menuOpen);
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  function search(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) navigate(`/variants?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <div className="flex h-full flex-col bg-ground">
      <RedStrip entries={banner?.red_strip ?? []} />
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-sidebar shrink-0 flex-col gap-4 p-3 md:flex">
          <p className="px-3 pt-3 font-semibold">Stock Sync</p>
          <Nav counts={banner?.counts} />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col md:pb-inset md:pr-inset">
          <header className="flex h-topbar shrink-0 items-center gap-3 px-4 md:px-0">
            <Button look="text" aria-label="Open menu" className="md:hidden" onClick={() => dispatch(openMenu())}>
              <Icon name="menu" />
            </Button>
            <form onSubmit={search} className="flex-1" role="search">
              <input
                aria-label="Search"
                placeholder="Search Suppliers, Listings, Variants"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="h-control w-full max-w-xl rounded-control border border-control bg-surface px-3 text-body"
              />
            </form>
            {fulfilledTimeStamp ? <span className="text-small text-muted">Updated {clock(fulfilledTimeStamp)}</span> : null}
            <Button look="text" onClick={() => void logout()}>Sign out</Button>
          </header>
          <Sheet>
            <NeedsCodePrompt />
            <Suspense fallback={<BlockState kind="loading" />}>
              <Outlet />
            </Suspense>
          </Sheet>
        </div>
      </div>
      {menuOpen ? (
        <div role="dialog" aria-modal="true" aria-label="Menu" className="fixed inset-0 z-10 flex flex-col gap-4 bg-ground p-4 md:hidden">
          <Button look="text" aria-label="Close menu" className="self-end" onClick={() => dispatch(closeMenu())}>
            <Icon name="close" />
          </Button>
          <Nav counts={banner?.counts} onNavigate={() => dispatch(closeMenu())} />
        </div>
      ) : null}
    </div>
  );
}
