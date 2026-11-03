import { createSlice } from "@reduxjs/toolkit";

/** Client-only UI state. Server data lives in the API slice. */
const ui = createSlice({
  name: "ui",
  initialState: { menuOpen: false },
  reducers: {
    openMenu: (s) => void (s.menuOpen = true),
    closeMenu: (s) => void (s.menuOpen = false),
  },
});

export const { openMenu, closeMenu } = ui.actions;
export default ui.reducer;
