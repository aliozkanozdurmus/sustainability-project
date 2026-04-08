"use client";

// Bu sayfa, evidence-center ekraninin ana deneyimini kurar.

import { useMemo, useState } from "react";
import { FileUp, Loader2, ScanLine, SearchCheck, Sparkles } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  ChecklistStack,
  fieldClassName,
  FormField,
  MetricPill,
  SectionHeading,
  StatChip,
  SubtleAlert,
  SurfaceCard,
} from "@/components/workbench-ui";
import {
  type DocumentUploadResponse,
  type ExtractionQueueResponse,
  type ExtractionResponse,
  type ExtractionStatusResponse,
  type IndexStatusResponse,
  useExtractDocumentMutation,
  useQueueDocumentExtractionMutation,
  useReadExtractionStatusMutation,
  useReadIndexStatusMutation,
  useUploadDocumentMutation,
} from "@/lib/api/documents";
import { useWorkspaceContext } from "@/lib/api/workspace-store";

export default function EvidenceCenterPage() {
  const workspace = useWorkspaceContext();

  const [documentType, setDocumentType] = useState("energy_invoice");
  const [issuedAt, setIssuedAt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [extractionId, setExtractionId] = useState("");
  const [extractionMode, setExtractionMode] = useState("ocr");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<DocumentUploadResponse | null>(null);
  const [extractionSync, setExtractionSync] = useState<ExtractionResponse | null>(null);
  const [extractionQueued, setExtractionQueued] = useState<ExtractionQueueResponse | null>(null);
  const [extractionStatus, setExtractionStatus] = useState<ExtractionStatusResponse | null>(null);
  const [indexStatus, setIndexStatus] = useState<IndexStatusResponse | null>(null);
  const uploadMutation = useUploadDocumentMutation(workspace);
  const extractMutation = useExtractDocumentMutation(workspace);
  const queueExtractMutation = useQueueDocumentExtractionMutation(workspace);
  const extractionStatusMutation = useReadExtractionStatusMutation(workspace);
  const indexStatusMutation = useReadIndexStatusMutation(workspace);
  const busy =
    uploadMutation.isPending ||
    extractMutation.isPending ||
    queueExtractMutation.isPending ||
    extractionStatusMutation.isPending ||
    indexStatusMutation.isPending;
  const qualityScore = extractionStatus?.quality_score ?? extractionSync?.quality_score ?? null;
  const chunkCount = extractionStatus?.chunk_count ?? extractionSync?.chunk_count ?? 0;
  const indexedChunkCount = indexStatus?.indexed_chunk_count ?? 0;
  const pipelineChecklist = useMemo(
    () => [
      {
        label: "Document uploaded",
        detail: uploaded?.document_id ?? "Upload a source file to generate a document id.",
        done: Boolean(uploaded),
        tone: (uploaded ? "good" : "neutral") as "good" | "neutral",
      },
      {
        label: "Extraction completed",
        detail: extractionStatus?.status ?? extractionSync?.status ?? extractionQueued?.status ?? "No extraction yet",
        done: Boolean(extractionSync || extractionStatus?.status === "completed"),
        tone: (
          extractionStatus?.status === "failed"
            ? "critical"
            : extractionSync || extractionStatus?.status === "completed"
              ? "good"
              : "attention"
        ) as "critical" | "good" | "attention",
      },
      {
        label: "Index available",
        detail: indexStatus?.status ?? "Index status not loaded yet.",
        done: indexStatus?.status === "completed",
        tone: (
          indexStatus?.status === "failed" ? "critical" : indexStatus?.status === "completed" ? "good" : "attention"
        ) as "critical" | "good" | "attention",
      },
    ],
    [extractionQueued, extractionStatus, extractionSync, indexStatus, uploaded],
  );

  async function handleUpload() {
    if (!workspace) {
      setError("Workspace not selected. Create/select workspace from New Report first.");
      return;
    }
    if (!selectedFile) {
      setError("Select a file to upload.");
      return;
    }

    setError(null);
    setNotice(null);
    try {
      const payload = await uploadMutation.mutateAsync({
        documentType,
        issuedAt,
        file: selectedFile,
      });
      setUploaded(payload);
      setActiveDocumentId(payload.document_id);
      setNotice(`Document uploaded: ${payload.document_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  async function handleExtractNow() {
    if (!workspace || !activeDocumentId.trim()) {
      setError("Workspace and document id are required.");
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const payload = await extractMutation.mutateAsync({
        documentId: activeDocumentId,
        extractionMode,
      });
      setExtractionSync(payload);
      setExtractionId(payload.extraction_id);
      setNotice(`Extraction completed: ${payload.extraction_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
    }
  }

  async function handleQueueExtract() {
    if (!workspace || !activeDocumentId.trim()) {
      setError("Workspace and document id are required.");
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const payload = await queueExtractMutation.mutateAsync({
        documentId: activeDocumentId,
        extractionMode,
      });
      setExtractionQueued(payload);
      setExtractionId(payload.extraction_id);
      setNotice(`Queued extraction: ${payload.extraction_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Queue extraction failed.");
    }
  }

  async function handleReadExtractionStatus() {
    if (!workspace || !activeDocumentId.trim() || !extractionId.trim()) {
      setError("Workspace, document id, and extraction id are required.");
      return;
    }
    setError(null);
    try {
      const payload = await extractionStatusMutation.mutateAsync({
        documentId: activeDocumentId,
        extractionId,
      });
      setExtractionStatus(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction status fetch failed.");
    }
  }

  async function handleReadIndexStatus() {
    if (!workspace || !activeDocumentId.trim() || !extractionId.trim()) {
      setError("Workspace, document id, and extraction id are required.");
      return;
    }
    setError(null);
    try {
      const payload = await indexStatusMutation.mutateAsync({
        documentId: activeDocumentId,
        extractionId,
      });
      setIndexStatus(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Index status fetch failed.");
    }
  }

  return (
    <AppShell
      activePath="/evidence-center"
      title="Evidence Ingest Workbench"
      subtitle="Capture source documents, run extraction, and inspect indexing health from a compact factory surface."
      actions={[
        { href: "/reports/new", label: "New Report Run" },
        { href: "/retrieval-lab", label: "Open Retrieval Lab" },
      ]}
    >
      {!workspace ? (
        <SubtleAlert tone="attention" title="Workspace required">
          Open New Report Run first so this workbench knows which tenant and project to ingest into.
        </SubtleAlert>
      ) : (
        <div className="flex flex-wrap gap-2">
          <StatChip label="tenant" value={workspace.tenantId} />
          <StatChip label="project" value={workspace.projectId} />
          <StatChip label="document" value={activeDocumentId || "pending"} tone={uploaded ? "good" : "neutral"} />
        </div>
      )}

      {error ? (
        <SubtleAlert tone="critical" title="Ingest issue">
          {error}
        </SubtleAlert>
      ) : null}
      {notice ? (
        <SubtleAlert tone="good" title="Workbench update">
          {notice}
        </SubtleAlert>
      ) : null}

      <div className="grid dense-grid xl:grid-cols-[1.1fr_0.9fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Ingest intake"
            title="Upload source evidence"
            description="Add the document type, optional issued date, and the raw file that should enter OCR and chunk indexing."
          />
          <div className="mt-4 grid dense-grid md:grid-cols-4">
            <FormField label="Document Type">
              <input className={fieldClassName()} value={documentType} onChange={(event) => setDocumentType(event.target.value)} />
            </FormField>
            <FormField label="Issued At" hint="optional">
              <input className={fieldClassName()} placeholder="2025-12-31T00:00:00Z" value={issuedAt} onChange={(event) => setIssuedAt(event.target.value)} />
            </FormField>
            <FormField label="File" className="md:col-span-2">
              <input className={fieldClassName("pt-2.5")} type="file" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
            </FormField>
          </div>
          <div className="mt-4">
            <Button type="button" onClick={() => void handleUpload()} disabled={busy || !workspace}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              Upload Evidence
            </Button>
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Pipeline health"
            title="Extraction and index pulse"
            description="A compact view of upload presence, extraction quality, and indexed chunk availability."
          />
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <MetricPill label="quality" value={qualityScore !== null ? `${qualityScore}` : "pending"} detail="Latest extraction quality score." tone={qualityScore !== null && qualityScore >= 80 ? "good" : "attention"} />
            <MetricPill label="chunks" value={chunkCount} detail="Chunks produced by the latest extraction pass." tone={chunkCount > 0 ? "good" : "neutral"} />
            <MetricPill label="indexed" value={indexedChunkCount} detail="Indexed chunk count returned by the search layer." tone={indexedChunkCount > 0 ? "good" : "attention"} />
            <MetricPill label="mode" value={extractionMode} detail="Current extraction mode for new jobs." tone="neutral" />
          </div>
          <div className="mt-4">
            <ChecklistStack items={pipelineChecklist} />
          </div>
        </SurfaceCard>
      </div>

      <div className="grid dense-grid xl:grid-cols-[0.92fr_1.08fr]">
        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Extraction control"
            title="Run OCR, queue jobs, and refresh status"
            description="Use the document id and extraction id controls to inspect the current ingest lifecycle."
          />
          <div className="mt-4 grid dense-grid md:grid-cols-3">
            <FormField label="Document ID">
              <input className={fieldClassName()} value={activeDocumentId} onChange={(event) => setActiveDocumentId(event.target.value)} />
            </FormField>
            <FormField label="Extraction Mode">
              <input className={fieldClassName()} value={extractionMode} onChange={(event) => setExtractionMode(event.target.value)} />
            </FormField>
            <FormField label="Extraction ID">
              <input className={fieldClassName()} value={extractionId} onChange={(event) => setExtractionId(event.target.value)} />
            </FormField>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => void handleExtractNow()} disabled={busy || !workspace}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
              Extract Now
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleQueueExtract()} disabled={busy || !workspace}>
              Queue Extract
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleReadExtractionStatus()} disabled={busy || !workspace}>
              Read Extraction Status
            </Button>
            <Button type="button" onClick={() => void handleReadIndexStatus()} disabled={busy || !workspace}>
              <SearchCheck className="h-4 w-4" />
              Read Index Status
            </Button>
          </div>
        </SurfaceCard>

        <SurfaceCard className="px-5 py-5">
          <SectionHeading
            eyebrow="Result ledger"
            title="Structured payload snapshots"
            description="Keep the raw payloads visible so ingest regressions remain easy to trace."
            action={<Sparkles className="h-4 w-4 text-[color:var(--accent-strong)]" />}
          />
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <article className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
              <h3 className="mb-2 text-sm font-semibold">Upload Result</h3>
              <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">{uploaded ? JSON.stringify(uploaded, null, 2) : "{}"}</pre>
            </article>
            <article className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
              <h3 className="mb-2 text-sm font-semibold">Extraction (sync)</h3>
              <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">{extractionSync ? JSON.stringify(extractionSync, null, 2) : "{}"}</pre>
            </article>
            <article className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
              <h3 className="mb-2 text-sm font-semibold">Extraction (queue)</h3>
              <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">{extractionQueued ? JSON.stringify(extractionQueued, null, 2) : "{}"}</pre>
            </article>
            <article className="rounded-[1.35rem] border border-[color:var(--border)] bg-white/58 p-4">
              <h3 className="mb-2 text-sm font-semibold">Status + Index</h3>
              <pre className="max-h-80 overflow-auto rounded-md bg-muted/45 p-3 text-xs">{JSON.stringify({ extractionStatus, indexStatus }, null, 2)}</pre>
            </article>
          </div>
        </SurfaceCard>
      </div>
    </AppShell>
  );
}
