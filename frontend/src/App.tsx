import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

type UserType = "owner" | "supplier";
type JobStatus =
  | "bidding"
  | "awarded"
  | "funded"
  | "in_progress"
  | "awaiting_confirmation"
  | "completed"
  | "disputed";
type SenderType = "human" | "agent" | "system";

type ApiUser = {
  id: number;
  email?: string;
  user_type: UserType;
  hedera_account_id: string;
  hedera_public_key: string;
};

type Room = { id: number; name: string; sq_meters: number };
type Home = { id: number; name: string; address: string; rooms: Room[] };
type Party = { id: number; hedera_account_id: string };
type JobSummary = {
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
type JobDetail = JobSummary & {
  access_notes?: string;
  available_times?: string;
  escrow_account_id?: string;
  hcs_topic_id?: string;
  accepted_bid?: { id: number; amount_tinybar: number } | null;
  creation_fee_paid?: boolean;
  updated_at?: string;
};
type Bid = {
  id: number;
  supplier?: Party;
  amount_tinybar: number;
  message?: string;
  status: string;
  created_at?: string;
};
type Photo = {
  id: number;
  cid: string;
  room?: Pick<Room, "id" | "name"> | null;
  uploaded_by?: Party;
  sequence: number;
  review_status?: "pending" | "passed" | "failed" | "needs_retake";
  review_notes?: string;
  created_at?: string;
};
type Message = {
  id: number;
  sender_user_id: number | null;
  sender: (Party & { user_type?: UserType }) | null;
  sender_type: SenderType;
  body: string;
  photo_ids: number[];
  photos?: Pick<Photo, "id" | "cid" | "sequence">[];
  created_at?: string;
};
type AuditEvent = {
  type: "job_created" | "job_completed" | "job_disputed";
  job_id: number;
  sequence_number: number;
  consensus_timestamp: string;
  tx_hash?: string;
};
type PaymentRequirements = {
  scheme: string;
  network: string;
  amount: string;
  asset: string;
  payTo: string;
  maxTimeoutSeconds: number;
  extra?: Record<string, string>;
};
type PendingJobPayment = {
  payload: JobForm;
  requirements: PaymentRequirements;
};
type JobForm = {
  home_id: number;
  title: string;
  description: string;
  suggested_price_tinybar: number;
  access_notes: string;
  available_times: string;
};

class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(typeof body === "object" && body && "error" in body ? String(body.error) : `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

function asArray<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && key in value) {
    const nested = (value as Record<string, unknown>)[key];
    return Array.isArray(nested) ? (nested as T[]) : [];
  }
  return [];
}

function tinybarToHbar(tinybar?: number | null) {
  if (!tinybar) return "0";
  return (tinybar / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function hbarToTinybar(hbar: string) {
  const value = Number.parseFloat(hbar || "0");
  return Math.round((Number.isFinite(value) ? value : 0) * 100_000_000);
}

function formatDate(value?: string) {
  if (!value) return "No timestamp";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusLabel(status?: string) {
  return (status ?? "unknown").replace(/_/g, " ");
}

function useApi(token: string | null) {
  return useCallback(
    async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
      const headers = new Headers(options.headers);
      const hasBody = options.body !== undefined;
      if (hasBody && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      if (token) headers.set("Authorization", `Bearer ${token}`);

      const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (response.status === 204) return undefined as T;

      const contentType = response.headers.get("Content-Type") ?? "";
      const body = contentType.includes("application/json") ? await response.json() : await response.text();
      if (!response.ok) throw new ApiError(response.status, body);
      return body as T;
    },
    [token],
  );
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem("escroweye.token"));
  const [user, setUser] = useState<ApiUser | null>(() => {
    const stored = localStorage.getItem("escroweye.user");
    return stored ? (JSON.parse(stored) as ApiUser) : null;
  });
  const [homes, setHomes] = useState<Home[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [bids, setBids] = useState<Bid[]>([]);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("Connect a mock wallet to start.");
  const [pendingPayment, setPendingPayment] = useState<PendingJobPayment | null>(null);
  const api = useApi(token);

  const persistSession = (nextToken: string, nextUser: ApiUser) => {
    localStorage.setItem("escroweye.token", nextToken);
    localStorage.setItem("escroweye.user", JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
  };

  const clearSession = () => {
    localStorage.removeItem("escroweye.token");
    localStorage.removeItem("escroweye.user");
    setToken(null);
    setUser(null);
    setHomes([]);
    setJobs([]);
    setSelectedJobId(null);
    setSelectedJob(null);
    setNotice("Signed out.");
  };

  const loadHomes = useCallback(async () => {
    if (!token) return;
    const result = await api<{ homes: Home[] } | Home[]>("/api/homes");
    setHomes(asArray<Home>(result, "homes"));
  }, [api, token]);

  const loadJobs = useCallback(async () => {
    if (!token) return;
    const result = await api<{ jobs: JobSummary[] } | JobSummary[]>("/api/jobs");
    const nextJobs = asArray<JobSummary>(result, "jobs");
    setJobs(nextJobs);
    setSelectedJobId((current) => current ?? nextJobs[0]?.id ?? null);
  }, [api, token]);

  const loadJobWorkspace = useCallback(
    async (jobId: number) => {
      const [job, bidResult, photoResult, messageResult, auditResult] = await Promise.all([
        api<JobDetail>(`/api/jobs/${jobId}`),
        api<{ bids: Bid[] } | Bid[]>(`/api/jobs/${jobId}/bids`).catch(() => ({ bids: [] })),
        api<{ photos: Photo[] } | Photo[]>(`/api/jobs/${jobId}/photos`).catch(() => ({ photos: [] })),
        api<{ messages: Message[] } | Message[]>(`/api/jobs/${jobId}/messages`).catch(() => ({ messages: [] })),
        api<{ events: AuditEvent[] } | AuditEvent[]>(`/api/jobs/${jobId}/audit-events`).catch(() => ({ events: [] })),
      ]);
      setSelectedJob(job);
      setBids(asArray<Bid>(bidResult, "bids"));
      setPhotos(asArray<Photo>(photoResult, "photos"));
      setMessages(asArray<Message>(messageResult, "messages"));
      setAuditEvents(asArray<AuditEvent>(auditResult, "events"));
    },
    [api],
  );

  const refreshAll = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      await Promise.all([loadHomes(), loadJobs()]);
      setNotice("Workspace refreshed.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to load workspace.");
    } finally {
      setLoading(false);
    }
  }, [loadHomes, loadJobs, token]);

  useEffect(() => {
    if (!token) return;
    refreshAll();
  }, [refreshAll, token]);

  useEffect(() => {
    if (!selectedJobId || !token) {
      setSelectedJob(null);
      return;
    }
    setLoading(true);
    loadJobWorkspace(selectedJobId)
      .catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Unable to load job."))
      .finally(() => setLoading(false));
  }, [loadJobWorkspace, selectedJobId, token]);

  const selectedHome = useMemo(() => homes.find((home) => home.id === selectedJob?.home.id), [homes, selectedJob]);

  async function handleLogin(form: LoginFormState) {
    setLoading(true);
    try {
      const challenge = await api<{ nonce: string; message: string }>("/api/auth/challenge", {
        method: "POST",
        body: JSON.stringify({ hedera_account_id: form.accountId }),
      });
      const login = await api<{ token: string; user: ApiUser }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          hedera_account_id: form.accountId,
          hedera_public_key: form.publicKey,
          signature: `mock_signature_for_${challenge.nonce}`,
          nonce: challenge.nonce,
          user_type: form.userType,
        }),
      });
      persistSession(login.token, login.user);
      setNotice(`Signed in as ${login.user.user_type} ${login.user.hedera_account_id}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateHome(payload: { name: string; address: string }) {
    await api<Home>("/api/homes", { method: "POST", body: JSON.stringify(payload) });
    setNotice("Home created.");
    await loadHomes();
  }

  async function handleAddRoom(homeId: number, payload: { name: string; sq_meters: number }) {
    await api<Room>(`/api/homes/${homeId}/rooms`, { method: "POST", body: JSON.stringify(payload) });
    setNotice("Room added.");
    await loadHomes();
  }

  async function createJob(payload: JobForm, paymentHeader?: string) {
    try {
      const result = await api<{ id: number; status: JobStatus }>("/api/jobs", {
        method: "POST",
        headers: paymentHeader ? { "X-PAYMENT": paymentHeader } : undefined,
        body: JSON.stringify(payload),
      });
      setPendingPayment(null);
      setNotice(`Job #${result.id} created.`);
      await loadJobs();
      setSelectedJobId(result.id);
    } catch (error) {
      if (error instanceof ApiError && error.status === 402 && typeof error.body === "object" && error.body) {
        const requirements = (error.body as { payment_requirements?: PaymentRequirements }).payment_requirements;
        if (requirements) {
          setPendingPayment({ payload, requirements });
          setNotice("x402 payment required. Approve payment, then replay the job request.");
          return;
        }
      }
      throw error;
    }
  }

  async function replayJobPayment(paymentHeader: string) {
    if (!pendingPayment) return;
    await createJob(pendingPayment.payload, paymentHeader || "mock-paid-x402-header");
  }

  async function mutateJob(action: () => Promise<unknown>, success: string) {
    if (!selectedJobId) return;
    setLoading(true);
    try {
      await action();
      setNotice(success);
      await Promise.all([loadJobs(), loadJobWorkspace(selectedJobId)]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setLoading(false);
    }
  }

  if (!user || !token) {
    return <LoginScreen loading={loading} notice={notice} onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">EscrowEye</p>
          <h1>Property cleaning escrow</h1>
        </div>
        <div className="session">
          <span className={`role role-${user.user_type}`}>{user.user_type}</span>
          <span>{user.hedera_account_id}</span>
          <button className="ghost-button" onClick={refreshAll} disabled={loading}>
            Refresh
          </button>
          <button className="ghost-button" onClick={clearSession}>
            Sign out
          </button>
        </div>
      </header>

      <main className="workspace">
        <aside className="sidebar">
          <Notice text={notice} loading={loading} />
          <HomesPanel homes={homes} onCreateHome={handleCreateHome} onAddRoom={handleAddRoom} />
          <JobCreatePanel homes={homes} pendingPayment={pendingPayment} onCreateJob={createJob} onReplayPayment={replayJobPayment} />
        </aside>

        <section className="job-column">
          <JobList jobs={jobs} selectedJobId={selectedJobId} onSelect={setSelectedJobId} />
          {selectedJob ? (
            <JobWorkspace
              user={user}
              job={selectedJob}
              selectedHome={selectedHome}
              bids={bids}
              photos={photos}
              auditEvents={auditEvents}
              onBid={(amountTinybar, message) =>
                mutateJob(
                  () => api(`/api/jobs/${selectedJob.id}/bids`, { method: "POST", body: JSON.stringify({ amount_tinybar: amountTinybar, message }) }),
                  "Bid placed.",
                )
              }
              onAward={(bidId) =>
                mutateJob(
                  () => api(`/api/jobs/${selectedJob.id}/award`, { method: "POST", body: JSON.stringify({ bid_id: bidId }) }),
                  "Bid awarded.",
                )
              }
              onFund={(signedTransaction) =>
                mutateJob(
                  () =>
                    api(`/api/jobs/${selectedJob.id}/fund`, {
                      method: "POST",
                      body: JSON.stringify({ signed_transaction: signedTransaction || "mock_hashpack_signed_transaction" }),
                    }),
                  "Escrow funded.",
                )
              }
              onMarkReady={(message) =>
                mutateJob(
                  () => api(`/api/jobs/${selectedJob.id}/mark-ready`, { method: "POST", body: JSON.stringify({ message }) }),
                  "Job marked ready.",
                )
              }
              onConfirm={() => {
                const body = { action: "confirm_job", job_id: selectedJob.id, timestamp: Date.now() };
                return mutateJob(
                  () =>
                    api(`/api/jobs/${selectedJob.id}/confirm`, {
                      method: "POST",
                      body: JSON.stringify({ signature: "mock_hashpack_confirmation_signature", message: JSON.stringify(body) }),
                    }),
                  "Job confirmed.",
                );
              }}
              onDispute={(reason) =>
                mutateJob(
                  () => api(`/api/jobs/${selectedJob.id}/dispute`, { method: "POST", body: JSON.stringify({ reason }) }),
                  "Dispute opened.",
                )
              }
            />
          ) : (
            <EmptyState title="No job selected" body="Create a job or select one from the list." />
          )}
        </section>

        <ConversationPanel
          job={selectedJob}
          messages={messages}
          photos={photos}
          rooms={selectedHome?.rooms ?? []}
          onSend={(body, photoIds) =>
            selectedJob
              ? mutateJob(
                  () => api(`/api/jobs/${selectedJob.id}/messages`, { method: "POST", body: JSON.stringify({ body, photo_ids: photoIds }) }),
                  "Message sent.",
                )
              : Promise.resolve()
          }
          onUpload={(files, roomId) =>
            selectedJob
              ? mutateJob(async () => {
                  const form = new FormData();
                  files.forEach((file) => form.append("photos", file));
                  if (roomId) form.append("room_id", String(roomId));
                  form.append("encrypted_keys", JSON.stringify({ mode: "mvp_mock", count: files.length }));
                  await api(`/api/jobs/${selectedJob.id}/photos`, { method: "POST", body: form });
                }, "Photos uploaded.")
              : Promise.resolve()
          }
        />
      </main>
    </div>
  );
}

type LoginFormState = { userType: UserType; accountId: string; publicKey: string };

function LoginScreen({ loading, notice, onLogin }: { loading: boolean; notice: string; onLogin: (form: LoginFormState) => Promise<void> }) {
  const [form, setForm] = useState<LoginFormState>({
    userType: "owner",
    accountId: "0.0.12345",
    publicKey: "302a300506032b6570032100mock",
  });

  return (
    <main className="login-screen">
      <section className="login-card">
        <div>
          <p className="eyebrow">EscrowEye MVP</p>
          <h1>Sign in with a mock HashPack persona</h1>
          <p className="muted">Uses the documented challenge and login endpoints with deterministic mock signatures.</p>
        </div>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            onLogin(form);
          }}
        >
          <Segmented
            value={form.userType}
            options={[
              ["owner", "Owner"],
              ["supplier", "Supplier"],
            ]}
            onChange={(value) => setForm((current) => ({ ...current, userType: value as UserType }))}
          />
          <label>
            Hedera account
            <input value={form.accountId} onChange={(event) => setForm((current) => ({ ...current, accountId: event.target.value }))} />
          </label>
          <label>
            Public key
            <input value={form.publicKey} onChange={(event) => setForm((current) => ({ ...current, publicKey: event.target.value }))} />
          </label>
          <button className="primary-button" disabled={loading}>
            Connect persona
          </button>
        </form>
        <Notice text={notice} loading={loading} />
      </section>
    </main>
  );
}

function Notice({ text, loading }: { text: string; loading?: boolean }) {
  return <div className="notice">{loading ? "Working..." : text}</div>;
}

function Segmented({ value, options, onChange }: { value: string; options: [string, string][]; onChange: (value: string) => void }) {
  return (
    <div className="segmented">
      {options.map(([optionValue, label]) => (
        <button key={optionValue} type="button" className={value === optionValue ? "active" : ""} onClick={() => onChange(optionValue)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function HomesPanel({
  homes,
  onCreateHome,
  onAddRoom,
}: {
  homes: Home[];
  onCreateHome: (payload: { name: string; address: string }) => Promise<void>;
  onAddRoom: (homeId: number, payload: { name: string; sq_meters: number }) => Promise<void>;
}) {
  const [name, setName] = useState("Beach House");
  const [address, setAddress] = useState("42 Ocean Drive");
  const [roomHomeId, setRoomHomeId] = useState("");
  const [roomName, setRoomName] = useState("Kitchen");
  const [roomSize, setRoomSize] = useState("20");

  useEffect(() => {
    if (!roomHomeId && homes[0]) setRoomHomeId(String(homes[0].id));
  }, [homes, roomHomeId]);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Homes and rooms</h2>
        <span>{homes.length}</span>
      </div>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          onCreateHome({ name, address });
        }}
      >
        <input aria-label="Home name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Home name" />
        <input aria-label="Home address" value={address} onChange={(event) => setAddress(event.target.value)} placeholder="Address" />
        <button className="secondary-button">Add home</button>
      </form>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (roomHomeId) onAddRoom(Number(roomHomeId), { name: roomName, sq_meters: Number(roomSize) });
        }}
      >
        <select value={roomHomeId} onChange={(event) => setRoomHomeId(event.target.value)}>
          {homes.map((home) => (
            <option key={home.id} value={home.id}>
              {home.name}
            </option>
          ))}
        </select>
        <div className="inline-grid">
          <input value={roomName} onChange={(event) => setRoomName(event.target.value)} placeholder="Room" />
          <input type="number" min="1" value={roomSize} onChange={(event) => setRoomSize(event.target.value)} placeholder="m2" />
        </div>
        <button className="secondary-button" disabled={!roomHomeId}>
          Add room
        </button>
      </form>
      <div className="list compact">
        {homes.map((home) => (
          <article key={home.id} className="mini-card">
            <strong>{home.name}</strong>
            <span>{home.address}</span>
            <small>{home.rooms.length ? home.rooms.map((room) => room.name).join(", ") : "No rooms yet"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function JobCreatePanel({
  homes,
  pendingPayment,
  onCreateJob,
  onReplayPayment,
}: {
  homes: Home[];
  pendingPayment: PendingJobPayment | null;
  onCreateJob: (payload: JobForm) => Promise<void>;
  onReplayPayment: (paymentHeader: string) => Promise<void>;
}) {
  const [paymentHeader, setPaymentHeader] = useState("mock-paid-x402-header");
  const [form, setForm] = useState({
    homeId: "",
    title: "Deep clean before guest arrival",
    description: "Clean all listed rooms, surfaces, floors, and bathrooms.",
    suggestedHbar: "50",
    accessNotes: "Gate code 1234, key under mat.",
    availableTimes: "Weekdays after 2pm",
  });

  useEffect(() => {
    if (!form.homeId && homes[0]) setForm((current) => ({ ...current, homeId: String(homes[0].id) }));
  }, [form.homeId, homes]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.homeId) return;
    onCreateJob({
      home_id: Number(form.homeId),
      title: form.title,
      description: form.description,
      suggested_price_tinybar: hbarToTinybar(form.suggestedHbar),
      access_notes: form.accessNotes,
      available_times: form.availableTimes,
    });
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Create job</h2>
        <span>x402</span>
      </div>
      <form className="stack" onSubmit={submit}>
        <select value={form.homeId} onChange={(event) => setForm((current) => ({ ...current, homeId: event.target.value }))}>
          {homes.map((home) => (
            <option key={home.id} value={home.id}>
              {home.name}
            </option>
          ))}
        </select>
        <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="Job title" />
        <textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Scope" />
        <input value={form.suggestedHbar} onChange={(event) => setForm((current) => ({ ...current, suggestedHbar: event.target.value }))} placeholder="Suggested HBAR" />
        <textarea value={form.accessNotes} onChange={(event) => setForm((current) => ({ ...current, accessNotes: event.target.value }))} placeholder="Access notes" />
        <input value={form.availableTimes} onChange={(event) => setForm((current) => ({ ...current, availableTimes: event.target.value }))} placeholder="Available times" />
        <button className="primary-button" disabled={!form.homeId}>
          Submit job
        </button>
      </form>
      {pendingPayment ? (
        <div className="payment-box">
          <strong>Payment required</strong>
          <span>
            {pendingPayment.requirements.amount} tinybar to {pendingPayment.requirements.payTo} on {pendingPayment.requirements.network}
          </span>
          <input value={paymentHeader} onChange={(event) => setPaymentHeader(event.target.value)} aria-label="x402 payment header" />
          <button className="secondary-button" onClick={() => onReplayPayment(paymentHeader)}>
            Replay paid request
          </button>
        </div>
      ) : null}
    </section>
  );
}

function JobList({ jobs, selectedJobId, onSelect }: { jobs: JobSummary[]; selectedJobId: number | null; onSelect: (id: number) => void }) {
  return (
    <section className="panel job-list-panel">
      <div className="panel-head">
        <h2>Jobs</h2>
        <span>{jobs.length}</span>
      </div>
      <div className="job-list">
        {jobs.map((job) => (
          <button key={job.id} className={`job-row ${selectedJobId === job.id ? "selected" : ""}`} onClick={() => onSelect(job.id)}>
            <span>
              <strong>{job.title}</strong>
              <small>{job.home.name}</small>
            </span>
            <span className={`status status-${job.status}`}>{statusLabel(job.status)}</span>
            <span>{tinybarToHbar(job.lowest_bid_tinybar ?? job.suggested_price_tinybar)} HBAR</span>
          </button>
        ))}
        {!jobs.length ? <EmptyState title="No jobs" body="Jobs will appear here after creation or backend seeding." /> : null}
      </div>
    </section>
  );
}

function JobWorkspace({
  user,
  job,
  selectedHome,
  bids,
  photos,
  auditEvents,
  onBid,
  onAward,
  onFund,
  onMarkReady,
  onConfirm,
  onDispute,
}: {
  user: ApiUser;
  job: JobDetail;
  selectedHome?: Home;
  bids: Bid[];
  photos: Photo[];
  auditEvents: AuditEvent[];
  onBid: (amountTinybar: number, message: string) => Promise<void>;
  onAward: (bidId: number) => Promise<void>;
  onFund: (signedTransaction: string) => Promise<void>;
  onMarkReady: (message: string) => Promise<void>;
  onConfirm: () => Promise<void>;
  onDispute: (reason: string) => Promise<void>;
}) {
  const [bidHbar, setBidHbar] = useState("45");
  const [bidMessage, setBidMessage] = useState("I can complete this within the requested window.");
  const [fundSignature, setFundSignature] = useState("mock_hashpack_signed_transaction");
  const [readyMessage, setReadyMessage] = useState("All rooms are complete and photos are uploaded.");
  const [disputeReason, setDisputeReason] = useState("Photos do not match the scope of work.");

  return (
    <section className="job-detail">
      <div className="detail-header">
        <div>
          <p className="eyebrow">Job #{job.id}</p>
          <h2>{job.title}</h2>
          <p>{job.description}</p>
        </div>
        <span className={`status status-${job.status}`}>{statusLabel(job.status)}</span>
      </div>

      <div className="metrics">
        <Metric label="Suggested" value={`${tinybarToHbar(job.suggested_price_tinybar)} HBAR`} />
        <Metric label="Accepted" value={job.accepted_bid ? `${tinybarToHbar(job.accepted_bid.amount_tinybar)} HBAR` : "None"} />
        <Metric label="Escrow" value={job.escrow_account_id ?? "Not funded"} />
        <Metric label="HCS topic" value={job.hcs_topic_id ?? "Pending"} />
      </div>

      <div className="two-column">
        <section className="panel">
          <h3>Scope</h3>
          <dl className="facts">
            <dt>Home</dt>
            <dd>{job.home.name}</dd>
            <dt>Address</dt>
            <dd>{job.home.address}</dd>
            <dt>Access</dt>
            <dd>{job.access_notes || "No access notes"}</dd>
            <dt>Times</dt>
            <dd>{job.available_times || "No availability set"}</dd>
            <dt>Rooms</dt>
            <dd>{selectedHome?.rooms.map((room) => `${room.name} (${room.sq_meters} m2)`).join(", ") || "Rooms unavailable"}</dd>
          </dl>
        </section>

        <section className="panel">
          <h3>Actions</h3>
          {user.user_type === "supplier" ? (
            <form
              className="stack"
              onSubmit={(event) => {
                event.preventDefault();
                onBid(hbarToTinybar(bidHbar), bidMessage);
              }}
            >
              <div className="inline-grid">
                <input value={bidHbar} onChange={(event) => setBidHbar(event.target.value)} placeholder="HBAR" />
                <button className="primary-button">Place bid</button>
              </div>
              <textarea value={bidMessage} onChange={(event) => setBidMessage(event.target.value)} />
            </form>
          ) : null}

          {user.user_type === "owner" ? (
            <div className="stack">
              <input value={fundSignature} onChange={(event) => setFundSignature(event.target.value)} placeholder="Signed transaction" />
              <button className="secondary-button" onClick={() => onFund(fundSignature)}>
                Fund escrow
              </button>
              <button className="primary-button" onClick={onConfirm}>
                Confirm complete
              </button>
            </div>
          ) : (
            <div className="stack">
              <textarea value={readyMessage} onChange={(event) => setReadyMessage(event.target.value)} />
              <button className="primary-button" onClick={() => onMarkReady(readyMessage)}>
                Mark ready
              </button>
            </div>
          )}

          <div className="stack">
            <textarea value={disputeReason} onChange={(event) => setDisputeReason(event.target.value)} />
            <button className="danger-button" onClick={() => onDispute(disputeReason)}>
              Open dispute
            </button>
          </div>
        </section>
      </div>

      <div className="two-column">
        <BidsPanel bids={bids} user={user} onAward={onAward} />
        <PhotosPanel photos={photos} />
      </div>

      <section className="panel">
        <div className="panel-head">
          <h3>HCS audit</h3>
          <span>{auditEvents.length}</span>
        </div>
        <div className="timeline">
          {auditEvents.map((event) => (
            <div key={`${event.sequence_number}-${event.type}`} className="timeline-item">
              <strong>{event.type}</strong>
              <span>{formatDate(event.consensus_timestamp)}</span>
              {event.tx_hash ? <small>{event.tx_hash}</small> : null}
            </div>
          ))}
          {!auditEvents.length ? <span className="muted">No audit events returned yet.</span> : null}
        </div>
      </section>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function BidsPanel({ bids, user, onAward }: { bids: Bid[]; user: ApiUser; onAward: (bidId: number) => Promise<void> }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Bids</h3>
        <span>{bids.length}</span>
      </div>
      <div className="list">
        {bids.map((bid) => (
          <article key={bid.id} className="mini-card bid-card">
            <div>
              <strong>{tinybarToHbar(bid.amount_tinybar)} HBAR</strong>
              <span>{bid.supplier?.hedera_account_id ?? "Supplier"}</span>
              <small>{bid.message || "No message"} · {bid.status}</small>
            </div>
            {user.user_type === "owner" ? (
              <button className="secondary-button" onClick={() => onAward(bid.id)}>
                Award
              </button>
            ) : null}
          </article>
        ))}
        {!bids.length ? <span className="muted">No bids returned yet.</span> : null}
      </div>
    </section>
  );
}

function PhotosPanel({ photos }: { photos: Photo[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Photos</h3>
        <span>{photos.length}</span>
      </div>
      <div className="photo-grid">
        {photos.map((photo) => (
          <article key={photo.id} className="photo-tile">
            <div className="photo-placeholder">#{photo.sequence}</div>
            <strong>{photo.room?.name ?? "Unassigned room"}</strong>
            <span>{photo.review_status ?? "pending"}</span>
            <small>{photo.cid}</small>
          </article>
        ))}
        {!photos.length ? <span className="muted">No photos uploaded yet.</span> : null}
      </div>
    </section>
  );
}

function ConversationPanel({
  job,
  messages,
  photos,
  rooms,
  onSend,
  onUpload,
}: {
  job: JobDetail | null;
  messages: Message[];
  photos: Photo[];
  rooms: Room[];
  onSend: (body: string, photoIds: number[]) => Promise<void>;
  onUpload: (files: File[], roomId?: number) => Promise<void>;
}) {
  const [body, setBody] = useState("Can the agent review the latest photos?");
  const [selectedPhotoIds, setSelectedPhotoIds] = useState<number[]>([]);
  const [roomId, setRoomId] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  return (
    <aside className="conversation">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Conversation</p>
          <h2>{job ? `Job #${job.id}` : "No job"}</h2>
        </div>
        <span>{messages.length}</span>
      </div>

      <div className="message-list">
        {messages.map((message) => (
          <article key={message.id} className={`message message-${message.sender_type}`}>
            <div className="message-meta">
              <strong>{message.sender_type === "human" ? message.sender?.hedera_account_id ?? "User" : message.sender_type}</strong>
              <span>{formatDate(message.created_at)}</span>
            </div>
            <p>{message.body}</p>
            {message.photos?.length ? (
              <div className="chips">
                {message.photos.map((photo) => (
                  <span key={photo.id}>photo #{photo.sequence}</span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {!messages.length ? <EmptyState title="No messages" body="Human, agent, and system messages render here." /> : null}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (!job || !body.trim()) return;
          onSend(body, selectedPhotoIds);
          setBody("");
          setSelectedPhotoIds([]);
        }}
      >
        <textarea value={body} onChange={(event) => setBody(event.target.value)} disabled={!job} />
        <div className="chips selectable">
          {photos.map((photo) => (
            <button
              key={photo.id}
              type="button"
              className={selectedPhotoIds.includes(photo.id) ? "active" : ""}
              onClick={() =>
                setSelectedPhotoIds((current) => (current.includes(photo.id) ? current.filter((id) => id !== photo.id) : [...current, photo.id]))
              }
            >
              photo #{photo.sequence}
            </button>
          ))}
        </div>
        <button className="primary-button" disabled={!job}>
          Send
        </button>
      </form>

      <form
        className="upload-box"
        onSubmit={(event) => {
          event.preventDefault();
          const files = Array.from(fileRef.current?.files ?? []);
          if (!job || !files.length) return;
          onUpload(files, roomId ? Number(roomId) : undefined);
          if (fileRef.current) fileRef.current.value = "";
        }}
      >
        <select value={roomId} onChange={(event) => setRoomId(event.target.value)}>
          <option value="">Agent assigns room</option>
          {rooms.map((room) => (
            <option key={room.id} value={room.id}>
              {room.name}
            </option>
          ))}
        </select>
        <input ref={fileRef} type="file" multiple accept="image/*" disabled={!job} />
        <button className="secondary-button" disabled={!job}>
          Upload photos
        </button>
      </form>
    </aside>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

export default App;
