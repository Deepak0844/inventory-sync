import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";

import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { RequireAuth } from "./RequireAuth";

const url = (p: string) => `http://localhost:3000/api${p}`;

function app() {
  return (
    <Routes>
      <Route path="/sign-in" element={<p>Sign in page</p>} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<p>Private page</p>} />
      </Route>
    </Routes>
  );
}

it("sends a signed-out visitor to the sign-in screen", async () => {
  server.use(http.get(url("/auth/me"), () => new HttpResponse(null, { status: 401 })));
  renderApp(app());
  expect(await screen.findByText("Sign in page")).toBeInTheDocument();
});

it("lets a signed-in user through", async () => {
  server.use(http.get(url("/auth/me"), () => HttpResponse.json({ username: "owner" })));
  renderApp(app());
  expect(await screen.findByText("Private page")).toBeInTheDocument();
});

it("shows neither page while the session is being checked", () => {
  server.use(http.get(url("/auth/me"), () => new Promise(() => {})));
  renderApp(app());
  expect(screen.queryByText("Private page")).not.toBeInTheDocument();
  expect(screen.queryByText("Sign in page")).not.toBeInTheDocument();
});
