import { Navigate, Outlet } from "react-router-dom";

import { useMeQuery } from "../../api/api";
import { BlockState } from "../ui/BlockState";

/** Lets signed-in users through. A 401 goes to sign-in; any other failure is shown, not hidden. */
export function RequireAuth() {
  const { isLoading, isSuccess, error, refetch } = useMeQuery();
  if (isLoading) return null;
  if (isSuccess) return <Outlet />;
  if (error && "status" in error && error.status === 401) return <Navigate to="/sign-in" replace />;
  return <BlockState kind="error" message="Couldn't reach the server." onRetry={() => void refetch()} />;
}
