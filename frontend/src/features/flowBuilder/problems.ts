import { createContext } from "react";

/** Problems per step id, so a card can show its own without every card re-rendering on typing. */
export const ProblemsContext = createContext<Record<string, string[]>>({});
