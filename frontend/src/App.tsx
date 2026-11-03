import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "./components/shell/RequireAuth";
import { Shell } from "./components/shell/Shell";

// One chunk per screen: a screen's code loads when it is opened.
const SignIn = lazy(() => import("./screens/SignIn"));
const Overview = lazy(() => import("./screens/Overview"));
const Suppliers = lazy(() => import("./screens/Suppliers"));
const SupplierDetail = lazy(() => import("./screens/SupplierDetail"));
const Listings = lazy(() => import("./screens/Listings"));
const Variants = lazy(() => import("./screens/Variants"));
const Approvals = lazy(() => import("./screens/Approvals"));
const Notifications = lazy(() => import("./screens/Notifications"));
const Orders = lazy(() => import("./screens/Orders"));
const Settings = lazy(() => import("./screens/Settings"));
const Flows = lazy(() => import("./screens/Flows"));

export default function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignIn />} />
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          <Route index element={<Overview />} />
          <Route path="suppliers" element={<Suppliers />} />
          <Route path="suppliers/:id" element={<SupplierDetail />} />
          <Route path="listings" element={<Listings />} />
          <Route path="variants" element={<Variants />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="orders" element={<Orders />} />
          <Route path="flows/*" element={<Flows />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
