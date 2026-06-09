export type UserType = "owner" | "supplier";

export type JobStatus =
  | "quote_requested"
  | "quote_received"
  | "quote_accepted"
  | "base_fee_paid"
  | "escrow_funded"
  | "accepted"
  | "processing"
  | "proof_uploaded"
  | "ai_reviewing"
  | "needs_revision"
  | "awaiting_owner_confirmation"
  | "cancelled"
  | "bidding"
  | "awarded"
  | "funded"
  | "in_progress"
  | "awaiting_confirmation"
  | "completed"
  | "disputed";

export type SenderType = "human" | "agent" | "system";

export type ApiUser = {
  id: number;
  email?: string;
  user_type: UserType;
  hedera_account_id: string;
  hedera_public_key: string;
};

export type Room = {
  id: number;
  name: string;
  sq_meters: number | null;
};

export type Home = {
  id: number;
  name: string;
  address: string;
  rooms: Room[];
};

export type Party = {
  id: number;
  hedera_account_id: string;
  user_type?: UserType;
};

export type JobSummary = {
  id: number;
  title: string;
  description: string;
  suggested_price_tinybar: number;
  status: JobStatus;
  home: Pick<Home, "id" | "name" | "address">;
  owner: Party;
  supplier: Party | null;
  bid_count?: number;
  lowest_bid_tinybar?: number | null;
  created_at?: string;
};

export type JobDetail = JobSummary & {
  access_notes?: string | null;
  available_times?: string | null;
  escrow_account_id?: string | null;
  hcs_topic_id?: string | null;
  accepted_bid?: { id: number; amount_tinybar: number } | null;
  creation_fee_paid?: boolean;
  updated_at?: string;
};

export type Bid = {
  id: number;
  supplier?: Party;
  amount_tinybar: number;
  message?: string | null;
  status: string;
  created_at?: string;
};

export type Photo = {
  id: number;
  cid: string;
  room?: Pick<Room, "id" | "name"> | null;
  uploaded_by?: Party;
  sequence: number;
  review_status?: "pending" | "passed" | "failed" | "needs_retake";
  review_notes?: string | null;
  created_at?: string;
};

export type Message = {
  id: number;
  sender_user_id: number | null;
  sender: Party | null;
  sender_type: SenderType;
  body: string;
  photo_ids: number[];
  photos?: Pick<Photo, "id" | "cid" | "sequence">[];
  created_at?: string;
};

export type AuditEvent = {
  type: string;
  job_id: number;
  sequence_number: number;
  consensus_timestamp: string;
  tx_hash?: string;
};

export type PaymentRequirements = {
  scheme: string;
  network: string;
  amount: string;
  asset: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra?: Record<string, string>;
};

export type JobForm = {
  home_id: number;
  title: string;
  description: string;
  suggested_price_tinybar: number;
  access_notes: string;
  available_times: string;
};

export type PendingJobPayment = {
  payload: JobForm;
  requirements: PaymentRequirements;
};

export type ServiceCategory = {
  id: number;
  name: string;
  slug: string;
  description: string;
};

export type WorkerResult = {
  id: number;
  supplier_id: number;
  name: string;
  profession: string;
  rating: number;
  average_rate: string;
  location: string;
  profile_image: string;
  completed_jobs: number;
  services: string[];
};
