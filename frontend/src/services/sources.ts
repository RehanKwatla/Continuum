import { api, apiDelete, apiGet } from "@/services/api";
import type {
  Source,
  SourceDeleteResponse,
  SourceListParams,
  SourceListResponse,
  UploadResponse,
} from "@/types";

export function listSources(
  projectId: string,
  params: SourceListParams = {},
): Promise<SourceListResponse> {
  return apiGet<SourceListResponse>(`/projects/${projectId}/sources`, { params });
}

export function getSource(sourceId: string): Promise<Source> {
  return apiGet<Source>(`/sources/${sourceId}`);
}

/** Source deletion returns a JSON body; `null` only if the API sent 204. */
export function deleteSource(sourceId: string): Promise<SourceDeleteResponse | null> {
  return apiDelete<SourceDeleteResponse>(`/sources/${sourceId}`);
}

/** Multipart upload. The backend performs all validation and parsing. */
export function uploadSources(
  projectId: string,
  files: File[],
  onProgress?: (percent: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);

  return api
    .post<UploadResponse>(`/projects/${projectId}/sources/upload`, form, {
      onUploadProgress: (event) => {
        if (!onProgress || !event.total) return;
        onProgress(Math.round((event.loaded / event.total) * 100));
      },
    })
    .then((response) => response.data);
}
