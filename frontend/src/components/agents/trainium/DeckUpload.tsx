"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";

type Course = {
  id: string;
  title: string;
  status: string;
  slides?: unknown[];
};

/** A readable sentence from whatever the server or the browser threw.
 *
 *  FastAPI returns `detail` as a string for a deliberate error but as an
 *  array of validation objects for a schema failure. Rendering the array
 *  gave an error message that was literally blank, which read as the upload
 *  failing for no reason at all.
 */
function describeError(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;

  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => (d as { msg?: string })?.msg)
      .filter((m): m is string => Boolean(m));
    if (parts.length) return parts.join(". ");
  }
  if (e instanceof Error && e.message) return e.message;
  return "Upload failed for an unknown reason. Check the server log.";
}

export function DeckUpload({ onUploaded }: { onUploaded: (course: Course) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    // The accept attribute only filters what the picker shows by default;
    // anyone can switch it to "All files" and choose a .docx. Checking here
    // means a wrong file is refused instantly, by name, instead of being
    // uploaded and rejected by a library error deep in the server.
    const name = file.name.toLowerCase();
    const kind = name.endsWith(".pdf") ? "pdf" : name.endsWith(".pptx") ? "pptx" : null;
    if (!kind) {
      // The old .ppt binary format is not Open XML, so python-pptx cannot
      // read it. Called out separately because "save as .pptx" is something
      // the admin can act on, where a generic refusal is not.
      const ext = file.name.includes(".") ? file.name.split(".").pop() : "";
      setError(
        name.endsWith(".ppt")
          ? "The older .ppt format is not supported. Open it in PowerPoint and save as .pptx."
          : ext
            ? `A .${ext} file cannot be used as teaching material. Upload a PowerPoint (.pptx) or a PDF.`
            : "Upload a PowerPoint (.pptx) or a PDF."
      );
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setBusy(true);
    setError(null);
    try {
      setProgress("Creating course...");
      const created = await api.post("/trainium/admin/courses", {
        title: file.name.replace(/\.[^.]+$/, ""),
      });

      // Rendering slides runs LibreOffice server-side, which is slow for a
      // large deck, so the default axios timeout is not enough here.
      setProgress("Uploading and rendering slides, this can take a minute...");
      const form = new FormData();
      form.append("file", file);
      const ingested = await api.post(
        // The two deck formats ingest the same way; the kind only picks
        // which extractor reads the pages.
        `/trainium/admin/courses/${created.data.id}/assets?kind=${kind}`,
        form,
        { timeout: 5 * 60 * 1000 }
      );

      const slideCount = Array.isArray(ingested.data.slides)
        ? ingested.data.slides.length
        : 0;
      setProgress(`Done, ${slideCount} slides ready.`);
      onUploaded(ingested.data as Course);
    } catch (e) {
      setError(describeError(e));
      setProgress("");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".pptx,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="mr-1.5 h-4 w-4" />
        {busy ? "Working..." : "Upload a deck"}
      </Button>
      {progress && <p className="mt-2 text-xs text-muted-foreground">{progress}</p>}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}
