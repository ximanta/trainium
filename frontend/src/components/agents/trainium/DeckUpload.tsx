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

export function DeckUpload({ onUploaded }: { onUploaded: (course: Course) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
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
        `/trainium/admin/courses/${created.data.id}/assets?kind=${
          file.name.toLowerCase().endsWith(".pdf") ? "pdf" : "pptx"
        }`,
        form,
        { timeout: 5 * 60 * 1000 }
      );

      const slideCount = Array.isArray(ingested.data.slides)
        ? ingested.data.slides.length
        : 0;
      setProgress(`Done, ${slideCount} slides ready.`);
      onUploaded(ingested.data as Course);
    } catch (e) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e instanceof Error ? e.message : "Upload failed");
      setError(detail);
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
