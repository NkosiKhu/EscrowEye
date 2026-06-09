import type { AuditEvent, Bid, JobDetail, JobSummary, Message, PaymentRequirements, Photo } from "../../types";

export type Profile = {
  firstName: string;
  lastName: string;
  location: string;
  serviceArea: string;
  photoUrl: string;
  paymentToken: "HBAR" | "Hedera token";
};

export type OwnerView = "browse" | "requests" | "messages" | "profile";
export type SupplierView = "jobs" | "earnings" | "messages" | "profile";
export type JobTab = "offers" | "active" | "archived";
export type RequestStep = "need" | "schedule" | "budget" | "summary" | "sent";
export type QuoteState = { job: JobSummary; amount: string } | null;
export type PendingServicePayment = { payload: ServiceRequestPayload; requirements: PaymentRequirements };

export type WorkerProfile = {
  id: number;
  name: string;
  profession: string;
  rating: string;
  rate: string;
  location: string;
  image: string;
  jobs: number;
};

export type ServiceRequestPayload = {
  title: string;
  description: string;
  address: string;
  location_description: string;
  schedule: string;
  budget_amount: number;
  category: string;
};

export type WorkspaceData = {
  job: JobDetail | null;
  bids: Bid[];
  photos: Photo[];
  messages: Message[];
  auditEvents: AuditEvent[];
};

export type RequestDraft = {
  title: string;
  description: string;
  schedule: string;
  budgetHbar: string;
  notes: string;
};
