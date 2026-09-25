"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Download, FileText, Search, Video } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";

type Run = {
  id: string;
  simulation_id: string;
  session_title: string;
  trainer_name: string;
  trainer_email: string;
  assigned_trainer_name: string;
  status: string;
  started_at?: string;
  actual_duration_s?: number;
  turns_taken?: number;
  report_status?: string | null;
  has_recording?: boolean;
};

function when(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Every delivery of every session, newest first.
 *
 *  Distinct from the session list, which shows what was *configured*. A
 *  shared join link means one configured session can be taught many times by
 *  different people, and "the report for this session" is ambiguous the
 *  moment that happens.
 */
export function RunList({ simulationId }: { simulationId?: string }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Run[]>("/trainium/admin/runs", {
        params: simulationId ? { simulation_id: simulationId } : undefined,
      })
      .then((r) => setRuns(r.data))
      .catch(() => setError("Could not load deliveries. Is the backend running?"));
  }, [simulationId]);

  // Filtered here rather than by refetching: the list is small enough that a
  // round trip per keystroke would only add lag.
  const shown = useMemo(() => {
    if (!runs) return null;
    const q = query.trim().toLowerCase();
    if (!q) return runs;
    return runs.filter((r) =>
      [r.trainer_name, r.trainer_email, r.session_title]
        .filter(Boolean)
        .some((f) => f.toLowerCase().includes(q))
    );
  }, [runs, query]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!shown) return <p className="text-sm text-muted-foreground">Loading...</p>;

  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by trainer, email or session"
          aria-label="Search deliveries"
          className="w-full rounded-md border py-2 pl-9 pr-3 text-sm"
        />
      </div>

      {shown.length === 0 ? (
        <p className="mt-6 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {query
            ? "Nothing matches that search."
            : "No sessions have been delivered yet. A delivery is recorded when a trainer opens a link and starts."}
        </p>
      ) : (
        <div className="mt-4 space-y-2">
          {shown.map((r) => {
            // Worth surfacing: the link was sent to one person and taught by
            // another, which happens when a trainer forwards it.
            const forwarded =
              r.assigned_trainer_name &&
              r.trainer_name &&
              r.assigned_trainer_name !== r.trainer_name;
            return (
              <div
                key={r.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    {r.trainer_name || "(name not given)"}
                    {r.status !== "complete" && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                        {r.status}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                    {r.trainer_email && <span>{r.trainer_email}</span>}
                    <span>{r.session_title}</span>
                    <span>{when(r.started_at)}</span>
                    {r.actual_duration_s ? (
                      <span>{Math.round(r.actual_duration_s / 60)} min</span>
                    ) : null}
                    {r.has_recording && (
                      <span className="flex items-center gap-1">
                        <Video className="h-3 w-3" />
                        recorded
                      </span>
                    )}
                  </p>
                  {forwarded && (
                    <p className="mt-1 text-xs text-amber-700">
                      Link was assigned to {r.assigned_trainer_name}
                    </p>
                  )}
                </div>

                <div className="flex shrink-0 items-center gap-1.5">
                  <Button asChild variant="outline" size="sm">
                    {/* Native anchor: this is a file download from the API,
                        not a route the router should try to handle. */}
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL}/trainium/admin/runs/${r.id}/transcript.csv`}
                      download
                    >
                      <Download className="mr-1.5 h-3.5 w-3.5" />
                      Transcript
                    </a>
                  </Button>
                  {r.report_status === "complete" && (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/trainium/report/${r.simulation_id}?run=${r.id}`}>
                        <FileText className="mr-1.5 h-3.5 w-3.5" />
                        Report
                      </Link>
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
