import type { Photo, WorkerResult } from "../../types";
import type { WorkerProfile } from "./models";

export function workerFromApi(worker: WorkerResult): WorkerProfile {
  return {
    id: worker.id,
    name: worker.name,
    profession: worker.profession,
    rating: String(worker.rating),
    rate: worker.average_rate,
    location: worker.location,
    image: worker.profile_image,
    jobs: worker.completed_jobs,
  };
}

export function photoFromProof(proof: Partial<Photo> & { storage_url?: string; validation_status?: string; file_type?: string }): Photo {
  return {
    id: Number(proof.id ?? 0),
    cid: String(proof.cid ?? ""),
    sequence: Number(proof.sequence ?? proof.id ?? 0),
    review_status: proof.review_status ?? (proof.validation_status === "passed" ? "passed" : "pending"),
    review_notes: proof.review_notes ?? proof.file_type ?? null,
    created_at: proof.created_at,
  };
}
