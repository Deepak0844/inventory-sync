import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";

import { makeStore } from "../store";

/** Renders with a fresh store and router. Absolute URLs because jsdom has no origin for msw. */
export function renderApp(ui: ReactElement, route = "/") {
  const store = makeStore();
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </Provider>,
  );
}
