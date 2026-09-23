"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Video } from "lucide-react";

import { api } from "@/api/axios";

type Evidence = {
  competency_key: string;
  quote: string;
  ts_start: number;
  speaker: string;
  source: "transcript" | "video";
  positive: boolean;
};

type Score = {
  competency_key: string;
  label: string;
  score: number;
  rationale: string;
  evidence: Evidence[];
};

type Report = {
  status: "pending" | "running" | "complete" | "failed";
  error?: string;
  summary?: string;
  strengths?: string[];
  improvements?: string[];
  scores?: Score[];
  video_scores?: Score[];
  video_analysed?: boolean;
};

function timecode(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** One competency: the score, why, and the moments it came from. Evidence is
 *  always shown rather than hidden behind a toggle, because a score whose
 *  basis is one click away invites trusting the number instead of reading it. */
function ScoreRow({ score }: { score: Score }) {
  return (
    <div className="border-t py-4 first:border-t-0">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="text-sm font-medium">{score.label}</h3>
        <span className="shrink-0 font-mono text-sm tabular-nums">
          <span className="text-lg font-semibold">{score.score}</span>
          <span className="text-muted-foreground">/5</span>
        </span>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{score.rationale}</p>

      {score.evidence.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {score.evidence.map((e, i) => (
            <li
              key={i}
              className={`border-l-2 py-0.5 pl-3 text-xs ${
                e.positive ? "border-green-400" : "border-amber-400"
              }`}
            >
              <span className="font-mono text-muted-foreground">
                {timecode(e.ts_start)}
              </span>{" "}
              <span className="text-slate-700">
                {e.source === "video" ? e.quote : `"${e.quote}"`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SessionReport({ simulationId }: { simulationId: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let stop = false;

    async function poll() {
      try {
        const r = await api.get<Report>(
          `/trainium/sessions/${simulationId}/report`
        );
        if (stop) return;
        setReport(r.data);
        // Analysis takes a minute or two, so the page waits rather than
        // making the trainer reload to find out whether it finished.
        if (r.data.status === "running" || r.data.status === "pending") {
          setTimeout(poll, 4000);
        }
      } catch {
        if (!stop) setMissing(true);
      }
    }

    poll();
    return () => {
      stop = true;
    };
  }, [simulationId]);

  if (missing) {
    return (
      <p className="text-sm text-muted-foreground">
        No report for this session yet. Reports are produced when a session ends.
      </p>
    );
  }

  if (!report) {
    return <p className="text-sm text-muted-foreground">Loading report...</p>;
  }

  if (report.status === "running" || report.status === "pending") {
    return (
      <div className="rounded-lg border p-8 text-center">
        <p className="text-sm font-medium">Working through your session</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Reading the transcript and watching the recording. This takes a minute or
          two.
        </p>
      </div>
    );
  }

  if (report.status === "failed") {
    return (
      <div className="flex gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div>
          <p className="text-sm font-medium">No report for this session</p>
          <p className="mt-1 text-xs text-muted-foreground">{report.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {report.summary && (
        <section>
          <p className="text-sm leading-relaxed">{report.summary}</p>
        </section>
      )}

      {(report.strengths?.length || report.improvements?.length) && (
        <section className="grid gap-4 sm:grid-cols-2">
          {report.strengths && report.strengths.length > 0 && (
            <div className="rounded-lg border border-green-200 bg-green-50/50 p-4">
              <h2 className="text-sm font-medium text-green-900">What worked</h2>
              <ul className="mt-2 space-y-1.5">
                {report.strengths.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-green-900">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.improvements && report.improvements.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4">
              <h2 className="text-sm font-medium text-amber-900">What to work on</h2>
              <ul className="mt-2 space-y-1.5">
                {report.improvements.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-amber-900">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section>
        <h2 className="text-sm font-medium">How you taught</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Scored from what you said, with the moments each score came from.
        </p>
        <div className="mt-2">
          {report.scores?.map((s) => (
            <ScoreRow key={s.competency_key} score={s} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <Video className="h-4 w-4 text-muted-foreground" />
          How you came across
        </h2>
        {report.video_analysed && report.video_scores?.length ? (
          <>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Scored from your camera, separately from what you said.
            </p>
            <div className="mt-2">
              {report.video_scores.map((s) => (
                <ScoreRow key={s.competency_key} score={s} />
              ))}
            </div>
          </>
        ) : (
          // Said plainly rather than shown as zeros: the trainer did not fail
          // these, there was simply nothing to watch.
          <p className="mt-2 rounded-lg border border-dashed p-4 text-xs text-muted-foreground">
            Your camera was off for this session, so delivery was not scored. Turn it
            on next time to get feedback on eye contact, posture and gesture.
          </p>
        )}
      </section>
    </div>
  );
}
