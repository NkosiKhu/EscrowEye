import { useCallback, useEffect, useMemo, useState } from "react";
import { asArray } from "../../format";
import { photoFromProof, workerFromApi } from "./adapters";
import { workers } from "./demoData";
import type { WorkspaceData, WorkerProfile, Profile } from "./models";
import type { ApiUser, AuditEvent, Bid, Home, JobSummary, Message, Photo, ServiceCategory } from "../../types";
import type { createEscrowEyeClient } from "../../services/escroweyeClient";

const emptyWorkspace: WorkspaceData = {
  job: null,
  bids: [],
  photos: [],
  messages: [],
  auditEvents: [],
};

type EscrowEyeClient = ReturnType<typeof createEscrowEyeClient>;

export function useWorkspaceData({
  api,
  token,
  user,
  profile,
  setNotice,
}: {
  api: EscrowEyeClient;
  token: string | null;
  user: ApiUser | null;
  profile: Profile;
  setNotice: (notice: string) => void;
}) {
  const [homes, setHomes] = useState<Home[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [supplierOffers, setSupplierOffers] = useState<JobSummary[]>([]);
  const [supplierActive, setSupplierActive] = useState<JobSummary[]>([]);
  const [supplierArchived, setSupplierArchived] = useState<JobSummary[]>([]);
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [workerResults, setWorkerResults] = useState<WorkerProfile[]>(workers);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceData>(emptyWorkspace);
  const [loading, setLoading] = useState(false);
  const [activeWorker, setActiveWorker] = useState(workers[0]);
  const [earnings, setEarnings] = useState<{ pending_earnings: number; past_earnings: number; total_earnings: number } | null>(null);
  const [supplierTxs, setSupplierTxs] = useState<Array<{ id: number; type: string; amount: number; token: string; status: string; hedera_tx_id: string | null; created_at: string }>>([]);

  const ownerJobs = useMemo(() => jobs.filter((job) => user && job.owner.id === user.id), [jobs, user]);
  const assignedJobs = useMemo(() => jobs.filter((job) => user && job.supplier?.id === user.id), [jobs, user]);
  const marketJobs = useMemo(
    () => supplierOffers.length ? supplierOffers : jobs.filter((job) => job.status === "bidding" || job.status === "quote_requested" || job.status === "quote_received"),
    [jobs, supplierOffers],
  );
  const activeSupplierJobs = useMemo(() => supplierActive.length ? supplierActive : assignedJobs.filter((job) => job.status !== "completed" && job.status !== "disputed"), [assignedJobs, supplierActive]);
  const archivedSupplierJobs = useMemo(() => supplierArchived.length ? supplierArchived : assignedJobs.filter((job) => job.status === "completed" || job.status === "disputed"), [assignedJobs, supplierArchived]);

  const loadHomes = useCallback(async () => {
    if (!token) return;
    const result = await api.homes();
    setHomes(asArray<Home>(result, "homes"));
  }, [api, token]);

  const loadJobs = useCallback(async () => {
    if (!token) return;
    if (user?.user_type === "supplier") {
      const [offers, active, archived] = await Promise.all([
        api.supplierOffers(),
        api.supplierActive(),
        api.supplierArchived(),
      ]);
      setSupplierOffers(offers.jobs);
      setSupplierActive(active.jobs);
      setSupplierArchived(archived.jobs);
      const nextJobs = [...active.jobs, ...offers.jobs, ...archived.jobs];
      setJobs(nextJobs);
      setSelectedJobId((current) => current ?? nextJobs[0]?.id ?? null);
      // Fetch earnings data for the supplier earnings panel
      api.supplierEarnings().then(setEarnings).catch(() => null);
      api.supplierTransactions().then((res) => setSupplierTxs(res.transactions)).catch(() => null);
      return;
    }
    const result = await api.ownerRequests();
    const nextJobs = asArray<JobSummary>(result, "requests");
    setJobs(nextJobs);
    setSelectedJobId((current) => current ?? nextJobs[0]?.id ?? null);
  }, [api, token, user?.user_type]);

  const loadMarketplace = useCallback(async () => {
    const [categoryResult, workerResult] = await Promise.all([
      api.serviceCategories(),
      api.workers(),
    ]);
    setCategories(categoryResult.categories);
    const nextWorkers = workerResult.workers.map(workerFromApi);
    setWorkerResults(nextWorkers);
    setActiveWorker((current) => nextWorkers.find((worker) => worker.id === current.id) ?? nextWorkers[0] ?? current);
  }, [api]);

  const loadJobWorkspace = useCallback(
    async (jobId: number) => {
      const [job, bidResult, photoResult, messageResult, auditResult] = await Promise.all([
        api.serviceRequest(jobId),
        api.quotes(jobId).catch(() => ({ quotes: [] })),
        api.proof(jobId).catch(() => ({ proof: [] })),
        api.messages(jobId).catch(() => ({ messages: [] })),
        api.auditEvents(jobId).catch(() => ({ events: [] })),
      ]);
      setWorkspace({
        job,
        bids: asArray<Bid>(bidResult, "quotes"),
        photos: asArray<Photo>(photoResult, "proof").map(photoFromProof),
        messages: asArray<Message>(messageResult, "messages"),
        auditEvents: asArray<AuditEvent>(auditResult, "events"),
      });
    },
    [api],
  );

  const refreshAll = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      await Promise.all([loadHomes(), loadJobs(), loadMarketplace()]);
      setNotice("Synced with EscrowEye API.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to load workspace.");
    } finally {
      setLoading(false);
    }
  }, [loadHomes, loadJobs, loadMarketplace, setNotice, token]);

  const resetWorkspace = useCallback(() => {
    setHomes([]);
    setJobs([]);
    setSupplierOffers([]);
    setSupplierActive([]);
    setSupplierArchived([]);
    setWorkspace(emptyWorkspace);
    setSelectedJobId(null);
    setEarnings(null);
    setSupplierTxs([]);
  }, []);

  useEffect(() => {
    if (token) refreshAll();
  }, [refreshAll, token]);

  useEffect(() => {
    if (!selectedJobId || !token) {
      setWorkspace(emptyWorkspace);
      return;
    }
    loadJobWorkspace(selectedJobId).catch((error: unknown) => setNotice(error instanceof Error ? error.message : "Unable to load job."));
  }, [loadJobWorkspace, selectedJobId, setNotice, token]);

  async function ensureHomeForRequest() {
    if (homes[0]) return homes[0];
    const home = await api.createHome({ name: "Primary property", address: profile.location || "Ikoyi, Lagos" });
    await loadHomes();
    return home;
  }

  return {
    activeSupplierJobs,
    activeWorker,
    archivedSupplierJobs,
    categories,
    earnings,
    ensureHomeForRequest,
    loadJobWorkspace,
    loadJobs,
    loading,
    marketJobs,
    ownerJobs,
    refreshAll,
    resetWorkspace,
    selectedJobId,
    setActiveWorker,
    setSelectedJobId,
    supplierTxs,
    workerResults,
    workspace,
  };
}
