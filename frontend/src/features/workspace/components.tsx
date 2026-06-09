import React, { useRef, useState } from "react";
import { formatDate, statusLabel, tinybarToHbar, truncateMiddle } from "../../format";
import type { ApiUser, AuditEvent, Bid, JobDetail, JobSummary, Message, Photo, ServiceCategory, UserType } from "../../types";
import { sampleJobs, serviceCategories } from "./demoData";
import type { JobTab, OwnerView, PendingServicePayment, Profile, QuoteState, RequestDraft, RequestStep, SupplierView, WorkerProfile } from "./models";

function Onboarding({ loading, notice, profile, onLogin }: { loading: boolean; notice: string; profile: Profile; onLogin: (form: { userType: UserType; accountId: string; publicKey: string; profile: Profile }) => Promise<void> }) {
  const [userType, setUserType] = useState<UserType>("owner");
  const [accountId, setAccountId] = useState("0.0.12345");
  const [publicKey, setPublicKey] = useState("302a300506032b6570032100mock");
  const [draft, setDraft] = useState<Profile>({ ...profile, firstName: profile.firstName || "Nkosi", lastName: profile.lastName || "Khumalo" });

  return (
    <main className="onboarding-desktop">
      <section className="onboarding-hero">
        <p className="eyebrow light">EscrowEye</p>
        <h1>Hire local service suppliers with escrow, proof, and AI validation.</h1>
        <p>Owners request quotes and fund jobs. Suppliers upload proof and get paid after EscrowEye verifies the work.</p>
      </section>
      <form
        className="onboarding-form"
        onSubmit={(event) => {
          event.preventDefault();
          onLogin({ userType, accountId, publicKey, profile: draft });
        }}
      >
        <div>
          <p className="eyebrow">Get started</p>
          <h2>Create profile</h2>
        </div>
        <div className="role-grid">
          <button type="button" className={userType === "owner" ? "role-card active" : "role-card"} onClick={() => setUserType("owner")}>
            <strong>Find and hire a service</strong>
            <span>Owner</span>
          </button>
          <button type="button" className={userType === "supplier" ? "role-card active" : "role-card"} onClick={() => setUserType("supplier")}>
            <strong>Earn money by providing services</strong>
            <span>Supplier</span>
          </button>
        </div>
        <div className="form-grid two">
          <label>First name<input value={draft.firstName} onChange={(event) => setDraft((current) => ({ ...current, firstName: event.target.value }))} /></label>
          <label>Last name<input value={draft.lastName} onChange={(event) => setDraft((current) => ({ ...current, lastName: event.target.value }))} /></label>
        </div>
        <div className="form-grid two">
          <label>Location<input value={draft.location} onChange={(event) => setDraft((current) => ({ ...current, location: event.target.value }))} /></label>
          <label>Service area<input value={draft.serviceArea} onChange={(event) => setDraft((current) => ({ ...current, serviceArea: event.target.value }))} /></label>
        </div>
        <div className="form-grid two">
          <label>Hedera account<input value={accountId} onChange={(event) => setAccountId(event.target.value)} /></label>
          <label>Payment preference<select value={draft.paymentToken} onChange={(event) => setDraft((current) => ({ ...current, paymentToken: event.target.value as Profile["paymentToken"] }))}><option>HBAR</option><option>Hedera token</option></select></label>
        </div>
        <label>Public key<input value={publicKey} onChange={(event) => setPublicKey(event.target.value)} /></label>
        <button className="primary-button" disabled={loading}>Create desktop workspace</button>
        <Notice text={notice} loading={loading} />
      </form>
    </main>
  );
}

function Sidebar({ user, profile, displayName, activeView, setOwnerView, setSupplierView, onRefresh, onSeedDemo, onSignOut, loading }: { user: ApiUser; profile: Profile; displayName: string; activeView: string; setOwnerView: (view: OwnerView) => void; setSupplierView: (view: SupplierView) => void; onRefresh: () => void; onSeedDemo: () => void; onSignOut: () => void; loading: boolean }) {
  const items = user.user_type === "owner"
    ? [["browse", "Browse Services"], ["requests", "My Requests"], ["messages", "Messages"], ["profile", "Profile"]]
    : [["jobs", "Jobs"], ["earnings", "Earnings"], ["messages", "Messages"], ["profile", "Profile"]];

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <span>EE</span>
        <div>
          <strong>EscrowEye</strong>
          <small>Hedera escrow</small>
        </div>
      </div>
      <div className="profile-mini">
        <img src={profile.photoUrl} alt="" />
        <span>
          <strong>{displayName}</strong>
          <small>{user.user_type} · {user.hedera_account_id}</small>
        </span>
      </div>
      <nav className="side-nav">
        {items.map(([value, label]) => (
          <button
            key={value}
            className={activeView === value ? "active" : ""}
            onClick={() => user.user_type === "owner" ? setOwnerView(value as OwnerView) : setSupplierView(value as SupplierView)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="sidebar-actions">
        <button className="outline-button" onClick={onRefresh} disabled={loading}>Refresh</button>
        <button className="outline-button" onClick={onSeedDemo} disabled={loading}>Seed demo</button>
        <button className="ghost-button" onClick={onSignOut}>Sign out</button>
      </div>
    </aside>
  );
}

function Topbar({ displayName, profile, notice }: { displayName: string; profile: Profile; notice: string }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Desktop workspace</p>
        <h1>Welcome, {displayName.split(" ")[0]}</h1>
      </div>
      <div className="topbar-right">
        <Notice text={notice} />
        <span className="token-pill">{profile.paymentToken}</span>
      </div>
    </header>
  );
}

function OwnerDesktop({
  view,
  profile,
  jobs,
  categories,
  workers,
  activeWorker,
  setActiveWorker,
  selectedJob,
  photos,
  auditEvents,
  requestStep,
  setRequestStep,
  pendingPayment,
  onSubmitRequest,
  onReplayPayment,
  onSelectJob,
  onConfirm,
  onDispute,
}: {
  view: OwnerView;
  profile: Profile;
  jobs: JobSummary[];
  categories: ServiceCategory[];
  workers: WorkerProfile[];
  activeWorker: WorkerProfile;
  setActiveWorker: (worker: WorkerProfile) => void;
  selectedJob: JobDetail | null;
  photos: Photo[];
  auditEvents: AuditEvent[];
  requestStep: RequestStep | null;
  setRequestStep: (step: RequestStep | null) => void;
  pendingPayment: PendingServicePayment | null;
  onSubmitRequest: (request: RequestDraft) => Promise<void>;
  onReplayPayment: (paymentHeader: string) => Promise<void> | null;
  onSelectJob: (id: number) => void;
  onConfirm: () => Promise<void>;
  onDispute: (reason: string) => Promise<void>;
}) {
  if (view === "messages") return <MessagesPanel messages={selectedJob ? [`Quote and escrow updates for ${selectedJob.title}`, "EscrowEye AI validation messages appear here."] : ["No active request selected."]} />;
  if (view === "profile") return <ProfilePanel profile={profile} role="Owner" />;
  if (view === "requests") return <OwnerRequests jobs={jobs} selectedJob={selectedJob} photos={photos} auditEvents={auditEvents} onSelectJob={onSelectJob} onConfirm={onConfirm} onDispute={onDispute} />;

  return (
    <section className="owner-grid">
      <div className="main-column">
        <HeroPanel
          title="Browse trusted suppliers"
          body="Find cleaning, maintenance, pool care, Airbnb turnover, carpentry, and repair professionals in your region."
          action="Request quote"
          onAction={() => setRequestStep("need")}
        />
        <CategoryPanel categories={categories} />
        <WorkerDirectory workers={workers} activeWorker={activeWorker} setActiveWorker={setActiveWorker} onRequest={() => setRequestStep("need")} />
      </div>
      <aside className="context-column">
        <WorkerProfileCard worker={activeWorker} onRequest={() => setRequestStep("need")} />
        <EscrowFlowCard />
      </aside>
      {requestStep ? <RequestQuoteModal worker={activeWorker} step={requestStep} setStep={setRequestStep} pendingPayment={pendingPayment} onSubmitRequest={onSubmitRequest} onReplayPayment={onReplayPayment} /> : null}
    </section>
  );
}

function SupplierDesktop({
  view,
  jobTab,
  setJobTab,
  profile,
  marketJobs,
  activeJobs,
  archivedJobs,
  selectedJob,
  bids,
  photos,
  messages,
  auditEvents,
  quoteState,
  setQuoteState,
  onSelectJob,
  onSendQuote,
  onMarkReady,
  onUpload,
}: {
  view: SupplierView;
  jobTab: JobTab;
  setJobTab: (tab: JobTab) => void;
  profile: Profile;
  marketJobs: JobSummary[];
  activeJobs: JobSummary[];
  archivedJobs: JobSummary[];
  selectedJob: JobDetail | null;
  bids: Bid[];
  photos: Photo[];
  messages: Message[];
  auditEvents: AuditEvent[];
  quoteState: QuoteState;
  setQuoteState: (state: QuoteState) => void;
  onSelectJob: (id: number) => void;
  onSendQuote: (job: JobSummary, amount: string) => Promise<void>;
  onMarkReady: (message: string) => Promise<void>;
  onUpload: (files: File[], roomId?: number) => Promise<void>;
}) {
  if (view === "messages") return <MessagesPanel messages={messages.length ? messages.map((message) => message.body) : ["Quote cards, proof updates, and owner confirmation prompts appear here."]} />;
  if (view === "profile") return <ProfilePanel profile={profile} role="Supplier" />;
  if (view === "earnings") return <EarningsPanel activeJobs={activeJobs} archivedJobs={archivedJobs} />;

  return (
    <section className="supplier-grid">
      <div className="main-column">
        <SupplierStats activeJobs={activeJobs} archivedJobs={archivedJobs} />
        <JobBoard
          jobTab={jobTab}
          setJobTab={setJobTab}
          marketJobs={marketJobs}
          activeJobs={activeJobs}
          archivedJobs={archivedJobs}
          onSelectJob={onSelectJob}
          setQuoteState={setQuoteState}
        />
      </div>
      <aside className="context-column">
        {selectedJob ? <SupplierJobDetail job={selectedJob} bids={bids} photos={photos} auditEvents={auditEvents} onQuote={() => setQuoteState({ job: selectedJob, amount: "220000" })} onMarkReady={onMarkReady} onUpload={onUpload} /> : <EmptyPanel title="Select a job" body="Choose an offer or active job to send quotes, upload proof, and trigger AI validation." />}
      </aside>
      {quoteState ? <SendQuoteModal state={quoteState} setState={setQuoteState} onSendQuote={onSendQuote} /> : null}
    </section>
  );
}

function HeroPanel({ title, body, action, onAction }: { title: string; body: string; action: string; onAction: () => void }) {
  return (
    <section className="hero-panel">
      <div>
        <p className="eyebrow light">EscrowEye marketplace</p>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
      <button className="primary-button" onClick={onAction}>{action}</button>
    </section>
  );
}

function CategoryPanel({ categories }: { categories: ServiceCategory[] }) {
  const visibleCategories = categories.length ? categories.map((category) => category.name) : serviceCategories;
  return (
    <section className="panel">
      <PanelHead title="Browse services" count={visibleCategories.length} />
      <div className="category-grid">
        {visibleCategories.map((category) => <button key={category}><span />{category}</button>)}
      </div>
    </section>
  );
}

function WorkerDirectory({ workers, activeWorker, setActiveWorker, onRequest }: { workers: WorkerProfile[]; activeWorker: WorkerProfile; setActiveWorker: (worker: WorkerProfile) => void; onRequest: () => void }) {
  return (
    <section className="panel">
      <PanelHead title="Workers in selected region" count={workers.length} />
      <div className="worker-table">
        {workers.map((worker) => (
          <button key={worker.id} className={activeWorker.id === worker.id ? "worker-row active" : "worker-row"} onClick={() => setActiveWorker(worker)}>
            <img src={worker.image} alt="" />
            <span><strong>{worker.name}</strong><small>{worker.profession} · {worker.location}</small></span>
            <b>{worker.rating}</b>
            <small>{worker.rate}</small>
            <em onClick={(event) => { event.stopPropagation(); onRequest(); }}>Request quote</em>
          </button>
        ))}
      </div>
    </section>
  );
}

function WorkerProfileCard({ worker, onRequest }: { worker: WorkerProfile; onRequest: () => void }) {
  return (
    <section className="panel worker-profile-card">
      <img src={worker.image} alt="" />
      <h2>{worker.name}</h2>
      <p>{worker.profession}</p>
      <div className="mini-stats">
        <Metric label="Rating" value={worker.rating} />
        <Metric label="Jobs" value={String(worker.jobs)} />
        <Metric label="Avg rate" value={worker.rate} />
      </div>
      <p className="muted">Verified supplier with portfolio proof, reviews, and escrow-safe payment flow.</p>
      <button className="primary-button" onClick={onRequest}>Request quote</button>
    </section>
  );
}

function OwnerRequests({ jobs, selectedJob, photos, auditEvents, onSelectJob, onConfirm, onDispute }: { jobs: JobSummary[]; selectedJob: JobDetail | null; photos: Photo[]; auditEvents: AuditEvent[]; onSelectJob: (id: number) => void; onConfirm: () => Promise<void>; onDispute: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState("Uploaded proof needs more evidence.");
  return (
    <section className="split-grid">
      <div className="panel">
        <PanelHead title="My service requests" count={jobs.length || sampleJobs.length} />
        <div className="job-list">
          {jobs.map((job) => <JobRow key={job.id} job={job} onClick={() => onSelectJob(job.id)} />)}
          {!jobs.length ? sampleJobs.map((job) => <StaticJobRow key={job.title} job={job} tag="Quote requested" />) : null}
        </div>
      </div>
      <div className="panel">
        {selectedJob ? (
          <div className="detail-stack">
            <PanelHead title="Owner job detail" />
            <h2>{selectedJob.title}</h2>
            <Fact label="Supplier" value={selectedJob.supplier?.hedera_account_id ?? "Waiting for quote"} />
            <Fact label="Budget" value={`${tinybarToHbar(selectedJob.suggested_price_tinybar)} HBAR`} />
            <Fact label="Base commitment fee" value={`${tinybarToHbar(selectedJob.suggested_price_tinybar * 0.2)} HBAR`} />
            <Fact label="Escrow" value={selectedJob.escrow_account_id ?? "Escrow pending"} />
            <AiValidation photos={photos} auditEvents={auditEvents} />
            <button className="primary-button" onClick={onConfirm}>Confirm satisfaction</button>
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
            <button className="outline-button" onClick={() => onDispute(reason)}>Open dispute</button>
          </div>
        ) : <EmptyPanel title="No request selected" body="Select a request to see quotes, proof, escrow, and AI validation." />}
      </div>
    </section>
  );
}

function RequestQuoteModal({ worker, step, setStep, pendingPayment, onSubmitRequest, onReplayPayment }: { worker: WorkerProfile; step: RequestStep; setStep: (step: RequestStep | null) => void; pendingPayment: PendingServicePayment | null; onSubmitRequest: (request: RequestDraft) => Promise<void>; onReplayPayment: (paymentHeader: string) => Promise<void> | null }) {
  const [request, setRequest] = useState<RequestDraft>({
    title: `${worker.profession} for 2 newly built two-storey buildings`,
    description: "Clean all windows and upload proof images for EscrowEye validation.",
    schedule: "Sat, 1 Mar 2025 · 9:00AM",
    budgetHbar: "2",
    notes: "Provide more information",
  });
  const [paymentHeader, setPaymentHeader] = useState("mock-paid-x402-header");

  return (
    <div className="modal-backdrop">
      <section className="desktop-modal">
        <button className="close-button" onClick={() => setStep(null)}>×</button>
        {step === "need" ? (
          <FlowStep title="What do you need help with?" hint="Describe the task for the supplier.">
            <textarea value={request.description} onChange={(event) => setRequest((current) => ({ ...current, description: event.target.value }))} />
            <button className="primary-button" onClick={() => setStep("schedule")}>Continue</button>
          </FlowStep>
        ) : null}
        {step === "schedule" ? (
          <FlowStep title="When do you need this?" hint="Choose a preferred time.">
            <div className="schedule-grid">{["9:00AM", "12:00PM", "3:00PM", "6:00PM"].map((time) => <button key={time} onClick={() => setRequest((current) => ({ ...current, schedule: `Sat, 1 Mar 2025 · ${time}` }))}>{time}</button>)}</div>
            <button className="primary-button" onClick={() => setStep("budget")}>Next</button>
          </FlowStep>
        ) : null}
        {step === "budget" ? (
          <FlowStep title="What is your budget?" hint="Set an expected HBAR budget.">
            <input value={request.budgetHbar} onChange={(event) => setRequest((current) => ({ ...current, budgetHbar: event.target.value }))} />
            <small className="info-strip">Base commitment fee is calculated as 20% after quote acceptance.</small>
            <button className="primary-button" onClick={() => setStep("summary")}>Next</button>
          </FlowStep>
        ) : null}
        {step === "summary" ? (
          <FlowStep title="Request summary" hint={request.title}>
            <Fact label="Supplier" value={worker.name} />
            <Fact label="Schedule" value={request.schedule} />
            <Fact label="Budget" value={`${request.budgetHbar} HBAR`} />
            <textarea value={request.notes} onChange={(event) => setRequest((current) => ({ ...current, notes: event.target.value }))} />
            <button className="primary-button" onClick={() => onSubmitRequest(request)}>Request quote</button>
            {pendingPayment ? (
              <div className="payment-box">
                <small>402 Payment Required: {pendingPayment.requirements.amount} tinybar</small>
                <input value={paymentHeader} onChange={(event) => setPaymentHeader(event.target.value)} />
                <button className="outline-button" onClick={() => onReplayPayment(paymentHeader)}>Replay paid request</button>
              </div>
            ) : null}
          </FlowStep>
        ) : null}
        {step === "sent" ? <SuccessPanel title="Request sent" body="Your service request was created and the audit trail is ready." /> : null}
      </section>
    </div>
  );
}

function SupplierStats({ activeJobs, archivedJobs }: { activeJobs: JobSummary[]; archivedJobs: JobSummary[] }) {
  return (
    <section className="stat-row">
      <Metric label="Pending earnings" value="₦570,000" />
      <Metric label="Active jobs" value={String(activeJobs.length)} />
      <Metric label="Paid jobs" value={String(archivedJobs.length)} />
      <Metric label="Rating" value="4.8" />
    </section>
  );
}

function JobBoard({ jobTab, setJobTab, marketJobs, activeJobs, archivedJobs, onSelectJob, setQuoteState }: { jobTab: JobTab; setJobTab: (tab: JobTab) => void; marketJobs: JobSummary[]; activeJobs: JobSummary[]; archivedJobs: JobSummary[]; onSelectJob: (id: number) => void; setQuoteState: (state: QuoteState) => void }) {
  const visibleJobs = jobTab === "offers" ? marketJobs : jobTab === "active" ? activeJobs : archivedJobs;
  return (
    <section className="panel">
      <div className="tab-head">
        <PanelHead title="Jobs" count={visibleJobs.length || sampleJobs.length} />
        <div className="tabs">
          {(["offers", "active", "archived"] as JobTab[]).map((tab) => <button key={tab} className={jobTab === tab ? "active" : ""} onClick={() => setJobTab(tab)}>{tab}</button>)}
        </div>
      </div>
      <div className="job-list">
        {visibleJobs.map((job) => <JobRow key={job.id} job={job} action={jobTab === "offers" ? "Send quote" : undefined} onClick={() => { onSelectJob(job.id); if (jobTab === "offers") setQuoteState({ job, amount: "220000" }); }} />)}
        {!visibleJobs.length ? sampleJobs.map((job) => <StaticJobRow key={job.title} job={job} tag={jobTab === "offers" ? "New offer" : jobTab === "archived" ? "Paid" : "Processing"} />) : null}
      </div>
    </section>
  );
}

function SupplierJobDetail({ job, bids, photos, auditEvents, onQuote, onMarkReady, onUpload }: { job: JobDetail; bids: Bid[]; photos: Photo[]; auditEvents: AuditEvent[]; onQuote: () => void; onMarkReady: (message: string) => Promise<void>; onUpload: (files: File[], roomId?: number) => Promise<void> }) {
  const [readyMessage, setReadyMessage] = useState("All service areas are complete and proof has been uploaded.");
  const fileRef = useRef<HTMLInputElement | null>(null);
  return (
    <section className="panel detail-stack">
      <PanelHead title="Job detail" />
      <h2>{job.title}</h2>
      <Fact label="Requested by" value={job.owner.hedera_account_id} />
      <Fact label="Location" value={job.home.address} />
      <Fact label="Scheduled for" value={job.available_times ?? "Sat, 1 Mar 2025"} />
      <Fact label="Budget" value={`${tinybarToHbar(job.suggested_price_tinybar)} HBAR`} />
      <p className="note-box">{job.access_notes || "Upload proof after completion. EscrowEye AI validates images/videos before owner confirmation."}</p>
      <div className="button-row">
        <button className="primary-button" onClick={onQuote}>Send Quote</button>
        <button className="outline-button">Private Message</button>
      </div>
      <div className="upload-card">
        <h3>Send job update</h3>
        <input ref={fileRef} type="file" multiple accept="image/*,video/*" />
        <button className="outline-button" onClick={() => onUpload(Array.from(fileRef.current?.files ?? []))}>Upload images/videos</button>
        <textarea value={readyMessage} onChange={(event) => setReadyMessage(event.target.value)} />
        <button className="primary-button" onClick={() => onMarkReady(readyMessage)}>Mark job complete</button>
      </div>
      <AiValidation photos={photos} auditEvents={auditEvents} />
      <small>{bids.length} quotes in this job</small>
    </section>
  );
}

function SendQuoteModal({ state, setState, onSendQuote }: { state: NonNullable<QuoteState>; setState: (state: QuoteState) => void; onSendQuote: (job: JobSummary, amount: string) => Promise<void> }) {
  const [amount] = useState(state.amount);
  const [sent, setSent] = useState(false);
  if (sent) {
    return (
      <div className="modal-backdrop">
        <section className="desktop-modal compact">
          <SuccessPanel title="Quote sent" body={`₦${Number(amount).toLocaleString()}.00`} />
        </section>
      </div>
    );
  }
  return (
    <div className="modal-backdrop">
      <section className="desktop-modal compact">
        <button className="close-button" onClick={() => setState(null)}>×</button>
        <h2>What is your quote?</h2>
        <p className="muted">What is the total price the client will pay?</p>
        <div className="money-input">₦{Number(amount || 0).toLocaleString()}.00</div>
        <small className="info-strip">The minimum amount is ₦10,000</small>
        <button className="primary-button" onClick={async () => { await onSendQuote(state.job, String(Number(amount || 0) / 100000)); setSent(true); }}>Send Quote</button>
      </section>
    </div>
  );
}

function EarningsPanel({ activeJobs, archivedJobs }: { activeJobs: JobSummary[]; archivedJobs: JobSummary[] }) {
  return (
    <section className="split-grid">
      <div className="hero-panel earnings">
        <p className="eyebrow light">Supplier earnings</p>
        <h2>₦570,000</h2>
        <p>{activeJobs.length} pending jobs · {archivedJobs.length} paid jobs</p>
      </div>
      <div className="panel">
        <PanelHead title="Transaction history" />
        {["Escrow release", "HBAR payout", "Base fee audit", "Pending escrow"].map((item, index) => (
          <div className="transaction-row" key={item}>
            <span>{item}<small>Hedera transaction #{index + 1}</small></span>
            <b>{index === 3 ? "Pending" : "Paid"}</b>
          </div>
        ))}
      </div>
    </section>
  );
}

function MessagesPanel({ messages }: { messages: string[] }) {
  return (
    <section className="panel">
      <PanelHead title="Messages" count={messages.length} />
      <div className="message-list">
        {messages.map((message) => <p key={message}>{message}</p>)}
      </div>
    </section>
  );
}

function ProfilePanel({ profile, role }: { profile: Profile; role: string }) {
  return (
    <section className="split-grid">
      <div className="panel profile-panel">
        <img src={profile.photoUrl} alt="" />
        <h2>{profile.firstName} {profile.lastName}</h2>
        <p>{role} · {profile.serviceArea}</p>
      </div>
      <div className="panel detail-stack">
        <PanelHead title={`${role} profile`} />
        <Fact label="Location" value={profile.location} />
        <Fact label="Payment" value={profile.paymentToken} />
        <Fact label="Portfolio" value={role === "Supplier" ? "12 completed jobs" : "3 service requests"} />
        <Fact label="Rating" value={role === "Supplier" ? "4.8" : "Verified owner"} />
      </div>
    </section>
  );
}

function EscrowFlowCard() {
  return (
    <section className="panel detail-stack">
      <PanelHead title="Escrow flow" />
      {["Owner accepts quote", "20% base fee paid", "Escrow funded in HBAR", "Supplier uploads proof", "AI validates work", "Owner confirms", "Payment released"].map((item, index) => (
        <div className="flow-row" key={item}><span>{index + 1}</span>{item}</div>
      ))}
    </section>
  );
}

function AiValidation({ photos, auditEvents }: { photos: Photo[]; auditEvents: AuditEvent[] }) {
  const passed = photos.some((photo) => photo.review_status === "passed");
  const needsEvidence = photos.some((photo) => photo.review_status === "needs_retake" || photo.review_status === "failed");
  const status = passed ? "Validation passed" : needsEvidence ? "Needs more evidence" : photos.length ? "AI reviewing" : "Waiting for proof";
  return (
    <div className="ai-panel">
      <h3>EscrowEye AI validation</h3>
      <Fact label="Status" value={status} />
      <Fact label="Confidence" value={passed ? "95%" : photos.length ? "72%" : "Pending"} />
      <Fact label="Audit trail" value={`${auditEvents.length} events`} />
      <div className="proof-grid">
        {photos.slice(0, 4).map((photo) => <span key={photo.id}>Proof #{photo.sequence}<small>{truncateMiddle(photo.cid, 8)}</small></span>)}
        {!photos.length ? <small>No images/videos uploaded yet.</small> : null}
      </div>
    </div>
  );
}

function JobRow({ job, action, onClick }: { job: JobSummary; action?: string; onClick: () => void }) {
  return (
    <button className="job-row" onClick={onClick}>
      <span><strong>{job.title}</strong><small>{job.home.address}</small></span>
      <span>{formatDate(job.created_at)}</span>
      <b>{tinybarToHbar(job.lowest_bid_tinybar ?? job.suggested_price_tinybar)} HBAR</b>
      {action ? <em>{action}</em> : <i className={`tag tag-${job.status}`}>{statusLabel(job.status)}</i>}
    </button>
  );
}

function StaticJobRow({ job, tag }: { job: (typeof sampleJobs)[number]; tag: string }) {
  return (
    <article className="job-row static">
      <span><strong>{job.title}</strong><small>{job.address}</small></span>
      <span>{job.date}</span>
      <b>{job.amount}</b>
      <i className="tag">{tag}</i>
    </article>
  );
}

function FlowStep({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="detail-stack">
      <h2>{title}</h2>
      <p className="muted">{hint}</p>
      {children}
    </div>
  );
}

function PanelHead({ title, count }: { title: string; count?: number }) {
  return (
    <div className="panel-head">
      <h2>{title}</h2>
      {count !== undefined ? <span>{count}</span> : null}
    </div>
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

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact-row">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <section className="panel empty-panel">
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}

function SuccessPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="success-panel">
      <span>✓</span>
      <small>Success</small>
      <h2>{title}</h2>
      <strong>{body}</strong>
    </div>
  );
}

function Notice({ text, loading }: { text: string; loading?: boolean }) {
  return <div className="notice">{loading ? "Working..." : text}</div>;
}

export {
  Onboarding,
  OwnerDesktop,
  Sidebar,
  SupplierDesktop,
  Topbar,
};
