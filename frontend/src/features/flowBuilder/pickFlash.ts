import { createContext } from "react";

/** The form field that just received a picked selector, so it can be flagged for a moment. */
export const PickFlashContext = createContext<string | null>(null);
