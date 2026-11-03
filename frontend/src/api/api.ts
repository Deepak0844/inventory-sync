import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

import type {
  AppNotification, Approval, Banner, FlaggedOrder, FlowDefinition, ImportResult, Listing,
  ListingQuery, LoginBody, ManualLogin, ManualLoginStatus, Mapping, Me, NewSupplier, Overview,
  PendingCode, Page, Run, Settings, NewTestRun, SettingsUpdate, Supplier, SupplierCredentials,
  TestResult, TestRun, VariantQuery, VariantRow,
} from "./types";

const tags = [
  "Auth", "Supplier", "Credentials", "Flow", "Runs", "PendingCode", "Listing", "Variant",
  "Approval", "Notification", "Order", "Overview", "Banner", "Settings", "TestRun",
  "ManualLogin",
] as const;

/** The one API slice. Endpoints are grouped by resource, in the order of docs/api.md. */
export const api = createApi({
  reducerPath: "api",
  // Tests set VITE_API_BASE to an absolute URL because Node's fetch cannot resolve a relative one.
  baseQuery: fetchBaseQuery({ baseUrl: import.meta.env.VITE_API_BASE ?? "/api", credentials: "same-origin" }),
  tagTypes: tags,
  endpoints: (b) => ({
    // auth
    me: b.query<Me, void>({ query: () => "/auth/me", providesTags: ["Auth"] }),
    login: b.mutation<void, LoginBody>({
      query: (body) => ({ url: "/auth/login", method: "POST", body }),
      invalidatesTags: ["Auth"],
    }),
    logout: b.mutation<void, void>({
      query: () => ({ url: "/auth/logout", method: "POST" }),
      invalidatesTags: ["Auth"],
    }),

    // suppliers
    suppliers: b.query<Supplier[], void>({
      query: () => "/suppliers",
      providesTags: ["Supplier"],
    }),
    supplier: b.query<Supplier, number>({
      query: (id) => `/suppliers/${id}`,
      providesTags: (_r, _e, id) => [{ type: "Supplier", id }],
    }),
    addSupplier: b.mutation<Supplier, NewSupplier>({
      query: (body) => ({ url: "/suppliers", method: "POST", body }),
      invalidatesTags: ["Supplier", "Overview"],
    }),
    updateSupplier: b.mutation<Supplier, { id: number } & Partial<Supplier>>({
      query: ({ id, ...body }) => ({ url: `/suppliers/${id}`, method: "PATCH", body }),
      invalidatesTags: ["Supplier", "Overview", "Banner"],
    }),
    deleteSupplier: b.mutation<void, number>({
      query: (id) => ({ url: `/suppliers/${id}`, method: "DELETE" }),
      invalidatesTags: ["Supplier", "Listing", "Variant", "Overview", "Banner"],
    }),
    credentials: b.query<SupplierCredentials, number>({
      query: (id) => `/suppliers/${id}/credentials`,
      providesTags: (_r, _e, id) => [{ type: "Credentials", id }],
    }),
    setCredentials: b.mutation<void, { id: number; username: string; password: string }>({
      query: ({ id, ...body }) => ({ url: `/suppliers/${id}/credentials`, method: "PUT", body }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "Credentials", id }],
    }),
    flow: b.query<FlowDefinition | null, number>({
      query: (id) => `/suppliers/${id}/flow`,
      providesTags: (_r, _e, id) => [{ type: "Flow", id }],
    }),
    setFlow: b.mutation<FlowDefinition, { id: number; flow: FlowDefinition }>({
      query: ({ id, flow }) => ({ url: `/suppliers/${id}/flow`, method: "PUT", body: flow }),
      invalidatesTags: (_r, _e, { id }) => [{ type: "Flow", id }],
    }),
    // test runs (flow builder)
    startTestRun: b.mutation<{ id: number }, NewTestRun>({
      query: (body) => ({ url: "/test-runs", method: "POST", body }),
    }),
    testRun: b.query<TestRun, number>({
      query: (id) => `/test-runs/${id}`,
      providesTags: (_r, _e, id) => [{ type: "TestRun", id }],
    }),
    startLogin: b.mutation<void, number>({
      query: (id) => ({ url: `/suppliers/${id}/login`, method: "POST" }),
      invalidatesTags: ["Supplier", "Runs", "PendingCode"],
    }),
    manualLoginStatus: b.query<ManualLoginStatus, number>({
      query: (id) => `/suppliers/${id}/manual-login`,
      providesTags: (_r, _e, id) => [{ type: "ManualLogin", id }],
    }),
    startManualLogin: b.mutation<ManualLogin, number>({
      query: (id) => ({ url: `/suppliers/${id}/manual-login`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => [{ type: "ManualLogin", id }],
    }),
    cancelManualLogin: b.mutation<void, number>({
      query: (id) => ({ url: `/suppliers/${id}/manual-login`, method: "DELETE" }),
      invalidatesTags: (_r, _e, id) => [{ type: "ManualLogin", id }],
    }),
    retrySupplier: b.mutation<void, number>({
      query: (id) => ({ url: `/suppliers/${id}/retry`, method: "POST" }),
      invalidatesTags: ["Supplier", "Banner", "Notification"],
    }),
    checkSupplier: b.mutation<void, number>({
      query: (id) => ({ url: `/suppliers/${id}/check`, method: "POST" }),
      invalidatesTags: ["Runs"],
    }),
    runs: b.query<{ items: Run[] }, number>({
      query: (id) => `/suppliers/${id}/runs`,
      providesTags: ["Runs"],
    }),

    // Login Code prompt
    pendingCodes: b.query<PendingCode[], void>({
      query: () => "/login-code/pending",
      providesTags: ["PendingCode"],
    }),
    submitCode: b.mutation<void, { supplierId: number; code: string }>({
      query: ({ supplierId, code }) => ({
        url: `/suppliers/${supplierId}/login-code`,
        method: "POST",
        body: { code },
      }),
      invalidatesTags: ["PendingCode", "Supplier", "Banner"],
    }),

    // listings, mappings, variants
    listings: b.query<Page<Listing>, ListingQuery>({
      query: (params) => ({ url: "/listings", params }),
      providesTags: ["Listing"],
    }),
    importListings: b.mutation<ImportResult, File>({
      query: (file) => {
        const body = new FormData();
        body.append("file", file);
        return { url: "/listings/import", method: "POST", body };
      },
      invalidatesTags: ["Listing", "Variant", "Supplier"],
    }),
    variants: b.query<Page<VariantRow>, VariantQuery>({
      query: (params) => ({ url: "/variants", params }),
      providesTags: ["Variant"],
    }),
    mappings: b.query<Mapping[], number>({
      query: (id) => `/variants/${id}/mappings`,
      providesTags: (_r, _e, id) => [{ type: "Variant", id }],
    }),
    setMappings: b.mutation<void, { id: number; mappings: Mapping[] }>({
      query: ({ id, mappings }) => ({ url: `/variants/${id}/mappings`, method: "PUT", body: mappings }),
      invalidatesTags: ["Variant", "Listing"],
    }),

    // approvals
    approvals: b.query<Approval[], void>({ query: () => "/approvals", providesTags: ["Approval"] }),
    approve: b.mutation<void, number>({
      query: (id) => ({ url: `/approvals/${id}/approve`, method: "POST" }),
      invalidatesTags: ["Approval", "Variant", "Overview", "Banner", "Notification"],
    }),
    reject: b.mutation<void, number>({
      query: (id) => ({ url: `/approvals/${id}/reject`, method: "POST" }),
      invalidatesTags: ["Approval", "Overview", "Banner", "Notification"],
    }),

    // notifications
    notifications: b.query<AppNotification[], { resolved: boolean }>({
      query: (params) => ({ url: "/notifications", params }),
      providesTags: ["Notification"],
    }),
    resolveNotification: b.mutation<void, number>({
      query: (id) => ({ url: `/notifications/${id}/resolve`, method: "POST" }),
      invalidatesTags: ["Notification", "Banner"],
    }),

    // orders
    flaggedOrders: b.query<FlaggedOrder[], void>({
      query: () => "/orders/flagged",
      providesTags: ["Order"],
    }),

    // overview and banner
    overview: b.query<Overview, void>({ query: () => "/overview", providesTags: ["Overview"] }),
    banner: b.query<Banner, void>({ query: () => "/banner", providesTags: ["Banner"] }),

    // settings
    settings: b.query<Settings, void>({ query: () => "/settings", providesTags: ["Settings"] }),
    updateSettings: b.mutation<Settings, SettingsUpdate>({
      query: (body) => ({ url: "/settings", method: "PUT", body }),
      invalidatesTags: ["Settings"],
    }),
    testShopify: b.mutation<TestResult, void>({
      query: () => ({ url: "/settings/shopify/test", method: "POST" }),
    }),
  }),
});

export const {
  useMeQuery, useLoginMutation, useLogoutMutation,
  useSuppliersQuery, useSupplierQuery, useAddSupplierMutation, useUpdateSupplierMutation,
  useDeleteSupplierMutation, useCredentialsQuery, useSetCredentialsMutation, useFlowQuery,
  useSetFlowMutation, useStartLoginMutation, useRetrySupplierMutation, useCheckSupplierMutation,
  useManualLoginStatusQuery, useStartManualLoginMutation, useCancelManualLoginMutation,
  useStartTestRunMutation, useTestRunQuery, useRunsQuery, usePendingCodesQuery, useSubmitCodeMutation, useListingsQuery,
  useImportListingsMutation, useVariantsQuery, useMappingsQuery, useSetMappingsMutation,
  useApprovalsQuery, useApproveMutation, useRejectMutation, useNotificationsQuery,
  useResolveNotificationMutation, useFlaggedOrdersQuery, useOverviewQuery, useBannerQuery,
  useSettingsQuery, useUpdateSettingsMutation, useTestShopifyMutation,
} = api;
