import { apiRequest } from "../api";
import type { ServiceRequestPayload } from "../features/workspace/models";
import type { ApiUser, AuditEvent, Bid, Home, JobDetail, JobStatus, JobSummary, Message, Photo, ServiceCategory, WorkerResult } from "../types";

export type LoginPayload = {
  hedera_account_id: string;
  hedera_public_key: string;
  signature: string;
  nonce: string;
  user_type: ApiUser["user_type"];
};

export function createEscrowEyeClient(token: string | null) {
  const request = <T,>(path: string, options?: RequestInit) => apiRequest<T>(token, path, options);

  return {
    authChallenge: (hederaAccountId: string) =>
      request<{ nonce: string; message: string }>("/api/auth/challenge", {
        method: "POST",
        body: JSON.stringify({ hedera_account_id: hederaAccountId }),
      }),

    login: (payload: LoginPayload) =>
      request<{ token: string; user: ApiUser }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    homes: () => request<{ homes: Home[] } | Home[]>("/api/homes"),

    createHome: (payload: { name: string; address: string }) =>
      request<Home>("/api/homes", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    ownerRequests: () => request<{ requests: JobSummary[] } | JobSummary[]>("/api/service-requests"),
    supplierOffers: () => request<{ jobs: JobSummary[] }>("/api/supplier/jobs/offers"),
    supplierActive: () => request<{ jobs: JobSummary[] }>("/api/supplier/jobs/active"),
    supplierArchived: () => request<{ jobs: JobSummary[] }>("/api/supplier/jobs/archived"),
    serviceCategories: () => request<{ categories: ServiceCategory[] }>("/api/service-categories"),
    workers: () => request<{ workers: WorkerResult[] }>("/api/workers"),

    serviceRequest: (jobId: number) => request<JobDetail>(`/api/service-requests/${jobId}`),
    quotes: (jobId: number) => request<{ quotes: Bid[] } | Bid[]>(`/api/service-requests/${jobId}/quotes`),
    proof: (jobId: number) => request<{ proof: Photo[] } | Photo[]>(`/api/service-requests/${jobId}/proof`),
    messages: (jobId: number) => request<{ messages: Message[] } | Message[]>(`/api/service-requests/${jobId}/messages`),
    auditEvents: (jobId: number) => request<{ events: AuditEvent[] } | AuditEvent[]>(`/api/service-requests/${jobId}/audit-events`),

    createServiceRequest: (payload: ServiceRequestPayload, paymentHeader?: string) =>
      request<{ id: number; status: JobStatus }>("/api/service-requests", {
        method: "POST",
        headers: paymentHeader ? { "X-PAYMENT": paymentHeader } : undefined,
        body: JSON.stringify(payload),
      }),

    seedDemo: () => request<{ job_id: number }>("/api/demo/seed", { method: "POST" }),

    acceptQuote: (quoteId: number) =>
      request(`/api/quotes/${quoteId}/accept`, {
        method: "POST",
      }),

    confirmSatisfaction: (jobId: number, payload: { signature: string; message: string }) =>
      request(`/api/service-requests/${jobId}/confirm-satisfaction`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    runAiValidation: (jobId: number) =>
      request(`/api/service-requests/${jobId}/ai-validation/run`, {
        method: "POST",
      }),

    releasePayment: (jobId: number) =>
      request(`/api/service-requests/${jobId}/release-payment`, {
        method: "POST",
      }),

    dispute: (jobId: number, reason: string) =>
      request(`/api/service-requests/${jobId}/dispute`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),

    sendQuote: (jobId: number, payload: { amount: number; message: string; scope: string; timeline: string }) =>
      request(`/api/service-requests/${jobId}/quotes`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    markComplete: (jobId: number, message: string) =>
      request(`/api/supplier/jobs/${jobId}/mark-complete`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),

    uploadProof: (jobId: number, form: FormData) =>
      request(`/api/service-requests/${jobId}/proof`, {
        method: "POST",
        body: form,
      }),

    fundEscrow: (jobId: number, transactionId?: string) =>
      request(`/api/service-requests/${jobId}/fund-escrow`, {
        method: "POST",
        body: JSON.stringify({ transaction_id: transactionId ?? null }),
      }),

    supplierEarnings: () =>
      request<{ pending_earnings: number; past_earnings: number; total_earnings: number }>("/api/supplier/earnings"),

    supplierTransactions: () =>
      request<{ transactions: Array<{ id: number; type: string; amount: number; token: string; status: string; hedera_tx_id: string | null; created_at: string }> }>("/api/supplier/transactions"),
  };
}
