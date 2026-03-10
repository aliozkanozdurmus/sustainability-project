"use client";

import { useEffect, useState } from "react";
import { FileUp, Loader2, ScanLine, SearchCheck } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  buildApiHeaders,
  getApiBaseUrl,
  getInitialWorkspaceContext,
  parseJsonOrThrow,
  persistWorkspaceContext,
  type WorkspaceContext,
} from "@/lib/api/client";

type DocumentUploadResponse = {
  document_id: string;
  tenant_id: string;
  project_id: string;
  filename: string;
  document_type: string;
  storage_uri: string;
  checksum: string;
  mime_type: string | null;
  status: string;
  ingested_at: string;
};

type ExtractionResponse = {
  extraction_id: string;
  source_document_id: string;
  status: string;
  provider: string;
  quality_score: number | null;
  extracted_text_uri: string | null;
  raw_payload_uri: string | null;
  chunk_count: number;
};

type ExtractionQueueResponse = {
  extraction_id: string;
  source_document_id: string;
  status: string;
  queue_job_id: string;
};

type ExtractionStatusResponse = {
  extraction_id: string;
  source_document_id: string;
  status: string;
  provider: string;
  extraction_mode: string;
  quality_score: number | null;
  chunk_count: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
};

type IndexStatusResponse = {
  extraction_id: string;
  source_document_id: string;
  status: string;
  index_provider: string;
  index_name: string;
  indexed_chunk_count: number;
  error_message: string | null;
};

function useWorkspace(): WorkspaceContext | null {
  const [workspace, setWorkspace] = useState<WorkspaceContext | null>(null);

  useEffect(() => {
    const initialWorkspace = getInitialWorkspaceContext();
    setWorkspace(initialWorkspace);
    if (initialWorkspace) {
      persistWorkspaceContext(initialWorkspace);
    }
  }, []);

  return workspace;
}

export default function EvidenceCenterPage() {
  const workspace = useWorkspace();

  const [documentType, setDocumentType] = useState("energy_invoice");
  const [issuedAt, setIssuedAt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [extractionId, setExtractionId] = useState("");
  const [extractionMode, setExtractionMode] = useState("ocr");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<DocumentUploadResponse | null>(null);
  const [extractionSync, setExtractionSync] = useState<ExtractionResponse | null>(null);
  const [extractionQueued, setExtractionQueued] = useState<ExtractionQueueResponse | null>(null);
  const [extractionStatus, setExtractionStatus] = useState<ExtractionStatusResponse | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatusResponse | null>(null);

  async function handleUpload() {
    if (!workspace) {
      setError("Workspace not selected. Create/select workspace from New Report first.");
      return;
    }
    if (!selectedFile) {
      setError("Select a file to upload.");
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const formData = new FormData();
      formData.set("tenant_id", workspace.tenantId);
      formData.set("project_id", workspace.projectId);
      formData.set("document_type", documentType);
      if (issuedAt.trim().length > 0) {
        formData.set("issued_at", issuedAt.trim());
      }
      formData.set("file", selectedFile);

      const response = await fetch(`${getApiBaseUrl()}/documents/upload`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId, { includeJsonContentType: false }),
        body: formData,
      });
      const payload = await parseJsonOrThrow<DocumentUploadResponse>(response);
      setUploaded(payload);
      setActiveDocumentId(payload.document_id);
      setNotice(`Document uploaded: ${payload.document_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleExtractNow() {
    if (!workspace || !activeDocumentId.trim()) {
      setError("Workspace and document id are required.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${getApiBaseUrl()}/documents/${encodeURIComponent(activeDocumentId)}/extract`, {
        method: "POST",
        headers: buildApiHeaders(workspace.tenantId),
        body: JSON.stringify({
          tenant_id: workspace.tenantId,
          project_id: workspace.projectId,
          extraction_mode: extractionMode,
        }),
      });
      const payload = await parseJsonOrThrow<ExtractionResponse>(response);
      setExtractionSync(payload);
      setExtractionId(payload.extraction_id);
      setNotice(`Extraction completed: ${payload.extraction_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleQueueExtract() {
    if (!workspace || !activeDocumentId.trim()) {
      setError("Workspace and document id are required.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `${getApiBaseUrl()}/documents/${encodeURIComponent(activeDocumentId)}/extract/queue`,
        {
          method: "POST",
          headers: buildApiHeaders(workspace.tenantId),
          body: JSON.stringify({
            tenant_id: workspace.tenantId,
            project_id: workspace.projectId,
            extraction_mode: extractionMode,
          }),
        },
      );
      const payload = await parseJsonOrThrow<ExtractionQueueResponse>(response);
      setExtractionQueued(payload);
      setExtractionId(payload.extraction_id);
      setNotice(`Queued extraction: ${payload.extraction_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Queue extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReadExtractionStatus() {
    if (!workspace || !activeDocumentId.trim() || !extractionId.trim()) {
      setError("Workspace, document id, and extraction id are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${getApiBaseUrl()}/documents/${encodeURIComponent(activeDocumentId)}/extractions/${encodeURIComponent(extractionId)}?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`,
        {
          headers: buildApiHeaders(workspace.tenantId),
        },
      );
      const payload = await parseJsonOrThrow<ExtractionStatusResponse>(response);
      setExtractionStatus(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction status fetch failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReadIndexStatus() {
    if (!workspace || !activeDocumentId.trim() || !extractionId.trim()) {
      setError("Workspace, document id, and extraction id are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${getApiBaseUrl()}/documents/${encodeURIComponent(activeDocumentId)}/extractions/${encodeURIComponent(extractionId)}/index-status?tenant_id=${encodeURIComponent(workspace.tenantId)}&project_id=${encodeURIComponent(workspace.projectId)}`,
        {
          headers: buildApiHeaders(workspace.tenantId),
        },
      );
      const payload = await parseJsonOrThrow<IndexStatusResponse>(response);
      setIndexStatus(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Index status fetch failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      activePath="/evidence-center"
      title="Evidence Center"
      subtitle="Upload source documents, run OCR extraction, and verify index state from UI."
      actions={[
        { href: "/reports/new", label: "New Report Wizard" },
        { href: "/retrieval-lab", label: "Open Retrieval Lab" },
      ]}
    >
      {!workspace ? (
        <div className="mb-4 rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          Workspace not selected. Configure tenant/project from New Report Wizard first.
        </div>
      ) : (
        <div className="mb-4 rounded-xl border bg-card px-4 py-3 text-xs text-muted-foreground">
          tenant_id={workspace.tenantId} | project_id={workspace.projectId}
        </div>
      )}

      {error ? (
        <div className="mb-4 rounded-xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mb-4 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
          {notice}
        </div>
      ) : null}

      <section className="rounded-xl border bg-card p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">1) Upload Evidence Document</h2>
        <div className="grid gap-3 md:grid-cols-4">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Document Type</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={documentType}
              onChange={(event) => setDocumentType(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Issued At (optional)</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              placeholder="2025-12-31T00:00:00Z"
              value={issuedAt}
              onChange={(event) => setIssuedAt(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span className="text-muted-foreground">File</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <div className="mt-3">
          <Button type="button" onClick={() => void handleUpload()} disabled={busy || !workspace}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
            Upload
          </Button>
        </div>
      </section>

      <section className="mt-4 rounded-xl border bg-card p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">2) Extraction and Index Status</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Document ID</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={activeDocumentId}
              onChange={(event) => setActiveDocumentId(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Extraction Mode</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={extractionMode}
              onChange={(event) => setExtractionMode(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Extraction ID</span>
            <input
              className="border-input bg-background w-full rounded-md border px-3 py-2"
              value={extractionId}
              onChange={(event) => setExtractionId(event.target.value)}
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void handleExtractNow()} disabled={busy || !workspace}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
            Extract Now
          </Button>
          <Button type="button" variant="outline" onClick={() => void handleQueueExtract()} disabled={busy || !workspace}>
            Queue Extract
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleReadExtractionStatus()}
            disabled={busy || !workspace}
          >
            Read Extraction Status
          </Button>
          <Button type="button" onClick={() => void handleReadIndexStatus()} disabled={busy || !workspace}>
            <SearchCheck className="h-4 w-4" />
            Read Index Status
          </Button>
        </div>
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-2">
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Upload Result</h3>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">
            {uploaded ? JSON.stringify(uploaded, null, 2) : "{}"}
          </pre>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Extraction (sync)</h3>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">
            {extractionSync ? JSON.stringify(extractionSync, null, 2) : "{}"}
          </pre>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Extraction (queue)</h3>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">
            {extractionQueued ? JSON.stringify(extractionQueued, null, 2) : "{}"}
          </pre>
        </article>
        <article className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold">Status + Index</h3>
          <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">
            {JSON.stringify({ extractionStatus, indexStatus }, null, 2)}
          </pre>
        </article>
      </section>
    </AppShell>
  );
}
