import { useEffect, useState } from "react";

const PHONE = "(max-width: 767px)";
const query = () => (typeof window.matchMedia === "function" ? window.matchMedia(PHONE) : null);

/** True below the tablet breakpoint, where the builder is read-only (docs/DESIGN.md, Phone). */
export function useIsPhone(): boolean {
  const [phone, setPhone] = useState(() => query()?.matches ?? false);
  useEffect(() => {
    const media = query();
    if (!media) return;
    const update = () => setPhone(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return phone;
}
