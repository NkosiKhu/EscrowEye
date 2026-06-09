import { useMemo, useState } from "react";
import { ApiError } from "./api";
import { useSession } from "./features/auth/useSession";
import {
  Onboarding,
  OwnerDesktop,
  Sidebar,
  SupplierDesktop,
  Topbar,
} from "./features/workspace/components";
import type { JobTab, OwnerView, PendingServicePayment, Profile, QuoteState, RequestDraft, RequestStep, ServiceRequestPayload, SupplierView } from "./features/workspace/models";
import { useWorkspaceData } from "./features/workspace/useWorkspaceData";
import { hbarToTinybar } from "./format";
import { createEscrowEyeClient } from "./services/escroweyeClient";
import type { PaymentRequirements, UserType } from "./types";
import { signWalletChallenge } from "./wallet";
import "./styles.css";

function App() {
  const { token, user, profile, persistSession, clearSession } = useSession();
  const [ownerView, setOwnerView] = useState<OwnerView>("browse");
  const [supplierView, setSupplierView] = useState<SupplierView>("jobs");
  const [jobTab, setJobTab] = useState<JobTab>("offers");
  const [requestStep, setRequestStep] = useState<RequestStep | null>(null);
  const [quoteState, setQuoteState] = useState<QuoteState>(null);
  const [pendingPayment, setPendingPayment] = useState<PendingServicePayment | null>(null);
  const [notice, setNotice] = useState("Choose a role to start.");
  const [actionLoading, setActionLoading] = useState(false);

  const api = useMemo(() => createEscrowEyeClient(token), [token]);
  const workspaceData = useWorkspaceData({ api, token, user, profile, setNotice });
  const displayName = [profile.firstName, profile.lastName].filter(Boolean).join(" ") || (user?.user_type === "supplier" ? "Supplier" : "Owner");
  const loading = actionLoading || workspaceData.loading;

  async function handleLogin(form: { userType: UserType; accountId: string; publicKey: string; profile: Profile }) {
    setActionLoading(true);
    try {
      const challenge = await api.authChallenge(form.accountId);
      const signedChallenge = await signWalletChallenge(challenge.message, `mock_signature_for_${challenge.nonce}`);
      const login = await api.login({
        hedera_account_id: signedChallenge.accountId ?? form.accountId,
        hedera_public_key: signedChallenge.publicKey ?? form.publicKey,
        signature: signedChallenge.signature,
        nonce: challenge.nonce,
        user_type: form.userType,
      });
      persistSession(login.token, login.user, form.profile);
      setNotice(`Connected ${login.user.user_type} profile ${form.accountId}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setActionLoading(false);
    }
  }

  function handleSignOut() {
    clearSession();
    workspaceData.resetWorkspace();
    setNotice("Signed out.");
  }

  async function createServiceRequest(payload: ServiceRequestPayload, paymentHeader?: string) {
    try {
      const result = await api.createServiceRequest(payload, paymentHeader);
      setPendingPayment(null);
      setRequestStep("sent");
      setNotice(`Request #${result.id} created with x402 payment.`);
      await workspaceData.loadJobs();
      workspaceData.setSelectedJobId(result.id);
    } catch (error) {
      if (error instanceof ApiError && error.status === 402 && error.body && typeof error.body === "object") {
        const requirements = (error.body as { payment_requirements?: PaymentRequirements }).payment_requirements;
        if (requirements) {
          setPendingPayment({ payload, requirements });
          setNotice("x402 payment required. Replay the paid request to create this service request.");
          return;
        }
      }
      throw error;
    }
  }

  async function submitOwnerRequest(request: RequestDraft) {
    await workspaceData.ensureHomeForRequest();
    await createServiceRequest({
      title: request.title,
      description: request.description,
      address: profile.location || "Ikoyi, Lagos",
      location_description: request.notes,
      schedule: request.schedule,
      budget_amount: hbarToTinybar(request.budgetHbar),
      category: "cleaning",
    });
  }

  async function mutateJob(action: () => Promise<unknown>, success: string) {
    if (!workspaceData.selectedJobId) return;
    setActionLoading(true);
    try {
      await action();
      setNotice(success);
      await Promise.all([workspaceData.loadJobs(), workspaceData.loadJobWorkspace(workspaceData.selectedJobId)]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setActionLoading(false);
    }
  }

  async function seedDemo() {
    setActionLoading(true);
    try {
      const seeded = await api.seedDemo();
      await workspaceData.refreshAll();
      workspaceData.setSelectedJobId(seeded.job_id);
      setNotice(`Demo seeded with job #${seeded.job_id}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to seed demo.");
    } finally {
      setActionLoading(false);
    }
  }

  if (!user || !token) {
    return <Onboarding loading={loading} notice={notice} profile={profile} onLogin={handleLogin} />;
  }

  return (
    <main className="desktop-app">
      <Sidebar
        user={user}
        profile={profile}
        displayName={displayName}
        activeView={user.user_type === "owner" ? ownerView : supplierView}
        setOwnerView={setOwnerView}
        setSupplierView={setSupplierView}
        onRefresh={workspaceData.refreshAll}
        onSeedDemo={seedDemo}
        onSignOut={handleSignOut}
        loading={loading}
      />
      <section className="desktop-main">
        <Topbar displayName={displayName} profile={profile} notice={notice} />
        {user.user_type === "owner" ? (
          <OwnerWorkspace
            profile={profile}
            view={ownerView}
            requestStep={requestStep}
            setRequestStep={setRequestStep}
            pendingPayment={pendingPayment}
            onSubmitRequest={submitOwnerRequest}
            onReplayPayment={(paymentHeader) => pendingPayment && createServiceRequest(pendingPayment.payload, paymentHeader || "mock-paid-x402-header")}
            onConfirm={() => {
              if (!workspaceData.workspace.job) return Promise.resolve();
              const body = { action: "confirm_job", job_id: workspaceData.workspace.job.id, timestamp: Date.now() };
              return mutateJob(
                () => api.confirmSatisfaction(workspaceData.workspace.job!.id, { signature: "mock_hashpack_confirmation_signature", message: JSON.stringify(body) }),
                "Owner satisfaction confirmed. Payment release event recorded.",
              );
            }}
            onDispute={(reason) =>
              workspaceData.workspace.job
                ? mutateJob(() => api.dispute(workspaceData.workspace.job!.id, reason), "Dispute opened for EscrowEye review.")
                : Promise.resolve()
            }
            workspaceData={workspaceData}
          />
        ) : (
          <SupplierWorkspace
            profile={profile}
            jobTab={jobTab}
            setJobTab={setJobTab}
            quoteState={quoteState}
            setQuoteState={setQuoteState}
            view={supplierView}
            onSendQuote={(job, amount) =>
              mutateJob(
                () => api.sendQuote(job.id, { amount: hbarToTinybar(amount), message: "Quote submitted from supplier desktop flow.", scope: "Service request scope", timeline: "1 day" }),
                "Quote sent.",
              )
            }
            onMarkReady={(message) =>
              workspaceData.workspace.job
                ? mutateJob(() => api.markComplete(workspaceData.workspace.job!.id, message), "Job marked ready for owner confirmation.")
                : Promise.resolve()
            }
            onUpload={(files, roomId) =>
              workspaceData.workspace.job
                ? mutateJob(async () => {
                    const form = new FormData();
                    files.forEach((file) => form.append("files", file));
                    if (roomId) form.append("room_id", String(roomId));
                    form.append("encrypted_keys", JSON.stringify({ mode: "mvp_mock", count: files.length }));
                    await api.uploadProof(workspaceData.workspace.job!.id, form);
                  }, "Proof uploaded for AI validation.")
                : Promise.resolve()
            }
            workspaceData={workspaceData}
          />
        )}
      </section>
    </main>
  );
}

type WorkspaceHook = ReturnType<typeof useWorkspaceData>;

function OwnerWorkspace({
  profile,
  view,
  requestStep,
  setRequestStep,
  pendingPayment,
  onSubmitRequest,
  onReplayPayment,
  onConfirm,
  onDispute,
  workspaceData,
}: {
  profile: Profile;
  view: OwnerView;
  requestStep: RequestStep | null;
  setRequestStep: (step: RequestStep | null) => void;
  pendingPayment: PendingServicePayment | null;
  onSubmitRequest: (request: RequestDraft) => Promise<void>;
  onReplayPayment: (paymentHeader: string) => Promise<void> | null;
  onConfirm: () => Promise<void>;
  onDispute: (reason: string) => Promise<void>;
  workspaceData: WorkspaceHook;
}) {
  return (
    <OwnerDesktop
      view={view}
      profile={profile}
      jobs={workspaceData.ownerJobs}
      categories={workspaceData.categories}
      workers={workspaceData.workerResults}
      activeWorker={workspaceData.activeWorker}
      setActiveWorker={workspaceData.setActiveWorker}
      selectedJob={workspaceData.workspace.job}
      photos={workspaceData.workspace.photos}
      auditEvents={workspaceData.workspace.auditEvents}
      requestStep={requestStep}
      setRequestStep={setRequestStep}
      pendingPayment={pendingPayment}
      onSubmitRequest={onSubmitRequest}
      onReplayPayment={onReplayPayment}
      onSelectJob={workspaceData.setSelectedJobId}
      onConfirm={onConfirm}
      onDispute={onDispute}
    />
  );
}

function SupplierWorkspace({
  profile,
  view,
  jobTab,
  setJobTab,
  quoteState,
  setQuoteState,
  onSendQuote,
  onMarkReady,
  onUpload,
  workspaceData,
}: {
  profile: Profile;
  view: SupplierView;
  jobTab: JobTab;
  setJobTab: (tab: JobTab) => void;
  quoteState: QuoteState;
  setQuoteState: (state: QuoteState) => void;
  onSendQuote: Parameters<typeof SupplierDesktop>[0]["onSendQuote"];
  onMarkReady: Parameters<typeof SupplierDesktop>[0]["onMarkReady"];
  onUpload: Parameters<typeof SupplierDesktop>[0]["onUpload"];
  workspaceData: WorkspaceHook;
}) {
  return (
    <SupplierDesktop
      view={view}
      jobTab={jobTab}
      setJobTab={setJobTab}
      profile={profile}
      marketJobs={workspaceData.marketJobs}
      activeJobs={workspaceData.activeSupplierJobs}
      archivedJobs={workspaceData.archivedSupplierJobs}
      selectedJob={workspaceData.workspace.job}
      bids={workspaceData.workspace.bids}
      photos={workspaceData.workspace.photos}
      messages={workspaceData.workspace.messages}
      auditEvents={workspaceData.workspace.auditEvents}
      quoteState={quoteState}
      setQuoteState={setQuoteState}
      onSelectJob={workspaceData.setSelectedJobId}
      onSendQuote={onSendQuote}
      onMarkReady={onMarkReady}
      onUpload={onUpload}
    />
  );
}

export default App;
