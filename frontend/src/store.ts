import { configureStore } from "@reduxjs/toolkit";

import { api } from "./api/api";
import ui from "./state/uiSlice";

export function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer, ui },
    middleware: (getDefault) => getDefault().concat(api.middleware),
  });
}

export const store = makeStore();
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
