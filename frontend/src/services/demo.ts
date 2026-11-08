import { apiGet, apiPost } from "@/services/api";
import type { PublicDemoStatus } from "@/types";

/** Fetch public demo mode status and pre-seeded workspace/project IDs. */
export function getPublicDemoStatus(): Promise<PublicDemoStatus> {
  return apiGet<PublicDemoStatus>("/public/demo");
}

/** Reset the disposable demo workspace to its pristine seeded state. */
export function resetPublicDemo(): Promise<PublicDemoStatus> {
  return apiPost<PublicDemoStatus>("/public/demo/reset");
}

