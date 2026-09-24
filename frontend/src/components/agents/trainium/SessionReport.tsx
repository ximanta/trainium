"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Download, Video } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";
import { ScoreRadar } from "@/components/agents/trainium/ScoreRadar";
import { SessionPlayer } from "@/components/agents/trainium/SessionPlayer";
import { downloadReportPdf } from "@/components/agents/trainium/reportPdf";
import type { Report, Score } from "@/components/agents/trainium/reportTypes";

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function tone(score: number) {
  if (score <= 2) return { bar: "bg-amber-600", text: "text-amber-700" };
  if (score >= 4) return { bar: "bg-green-700", text: "text-green-800" };
  return { bar: "bg-indigo-600", text: "text-slate-900" };
}

/** Five pips instead of a number alone: the shape of a 2 against a 5 reads
 *  before the digit does. */
function Pips({ score }: { score: number }) {
  return (
    <span className="flex gap-[3px]" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={`h-[7px] w-[7px] rounded-sm ${
            i <= score ? tone(score).bar : "bg-slate-200"
          }`}
        />
      ))}
    </span>
  );
}

/** One criterion: score, reasoning, and the moments it rests on. Evidence is
 *  always visible rather than behind a toggle, so the number is read together
 *  with its basis. */
function Criterion({
  score,
  onSeek,
}: {
  score: Score;
  onSeek?: (seconds: number) => void;
}) {
  const t = tone(score.score);
  return (
    <div className="border-b py-4 last:border-b-0">
      <div className="flex items-baseline gap-3">
        <h3 className="flex-1 text-sm font-medium">{score.label}</h3>
        <span className={`font-mono text-base tabular-nums ${t.text}`}>
          {score.score}
          <span className="text-xs text-muted-foreground">/5</span>
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${t.bar}`} style={{ width: `${score.score * 20}%` }} />
      </div>
      <p className="mt-2.5 text-sm leading-relaxed text-muted-foreground">
        {score.rationale}
      </p>
      {score.evidence.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5">
          {score.evidence.map((e, i) => (
            <li
              key={i}
              className={`border-l-2 pl-3 text-xs leading-relaxed ${
                e.positive ? "border-green-400" : "border-amber-400"
              }`}
            >
              {onSeek ? (
                <button
                  type="button"
                  onClick={() => onSeek(e.ts_start)}
                  className="cursor-pointer font-mono text-muted-foreground underline decoration-dotted underline-offset-2 transition-colors hover:text-indigo-700"
                  aria-label={`Play the session from ${clock(e.ts_start)}`}
                >
                  {clock(e.ts_start)}
                </button>
              ) : (
                <span className="font-mono text-muted-foreground">{clock(e.ts_start)}</span>
              )}{" "}
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
  const videoRef = useRef<HTMLVideoElement | null>(null);

  /** Jump the recording to a moment and play it. Scrolls the player into view
   *  first, since the timecode clicked may be far down the page. */
  function seekTo(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    video.scrollIntoView({ behavior: "smooth", block: "center" });
    void video.play().catch(() => {
      // Autoplay can be refused; the seek still happened, so the trainer can
      // press play themselves.
    });
  }

  useEffect(() => {
    let stop = false;

    async function poll() {
      try {
        const r = await api.get<Report>(`/trainium/sessions/${simulationId}/report`);
        if (stop) return;
        setReport(r.data);
        // Analysis takes a minute or two, so the page waits rather than making
        // the trainer reload to find out whether it finished.
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
      <div className="rounded-xl border p-10 text-center">
        <p className="text-sm font-medium">Working through your session</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Reading the transcript and watching the recording. This takes a minute or two.
        </p>
      </div>
    );
  }

  if (report.status === "failed") {
    return (
      <div className="flex gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div>
          <p className="text-sm font-medium">No report for this session</p>
          <p className="mt-1 text-xs text-muted-foreground">{report.error}</p>
        </div>
      </div>
    );
  }

  const spoken = report.scores ?? [];
  const delivery = report.video_scores ?? [];
  const assessed = [...spoken, ...delivery];
  const skipped = report.undetermined ?? [];
  const meta = report.session;
  const learners = meta?.persona_ids?.length ?? 0;
  const date = new Date(report.created_at ?? Date.now()).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  // Highest first, so the radar legend opens on a strength and the eye finds
  // the weak end by travelling rather than hunting.
  const ranked = [...assessed].sort((a, b) => b.score - a.score);

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-widest text-indigo-700">
            Session report
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">
            {meta?.title || "Session report"}
          </h1>
          <p className="mt-1.5 font-mono text-xs text-muted-foreground">
            {[date, meta?.trainer_name, `${meta?.duration_min ?? 0} min`, `${learners} learners`]
              .filter(Boolean)
              .join("  ·  ")}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() =>
            downloadReportPdf(report, {
              title: meta?.title ?? "Session",
              trainerName: meta?.trainer_name ?? "",
              durationMin: meta?.duration_min ?? 0,
              learners,
              date,
            })
          }
        >
          <Download className="mr-1.5 h-4 w-4" />
          Download PDF
        </Button>
      </div>

      {report.summary && (
        <p className="mt-6 max-w-[70ch] leading-relaxed text-slate-700">{report.summary}</p>
      )}

      {/* Coverage sits apart from the scores because it is measured, not
          judged. Keeping it separate is what lets a reader see "explained
          well, but barely any of it", which one blended number cannot say. */}
      {report.coverage && report.coverage.slides_total > 0 && (
        <div className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl border bg-slate-50 px-5 py-4">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Material covered
            </p>
            <p className="mt-1 flex items-baseline gap-2">
              <span
                className={`font-mono text-xl font-semibold tabular-nums ${
                  report.coverage.met_threshold ? "text-green-800" : "text-amber-700"
                }`}
              >
                {Math.round(report.coverage.fraction * 100)}%
              </span>
              <span className="text-sm text-muted-foreground">
                reached slide {report.coverage.furthest_slide} of{" "}
                {report.coverage.slides_total}
              </span>
            </p>
          </div>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Time used
            </p>
            <p className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-xl font-semibold tabular-nums">
                {Math.round(report.coverage.elapsed_min)}
                <span className="text-sm font-normal text-muted-foreground">
                  /{report.coverage.planned_min} min
                </span>
              </span>
            </p>
          </div>
          <p className="max-w-[34ch] text-xs leading-relaxed text-muted-foreground">
            Measured from the deck, not scored. The criteria below judge how well
            you taught what you did cover.
          </p>
        </div>
      )}

      {/* Profile: the whole assessed picture before any detail. */}
      {ranked.length >= 3 && (
        <section className="mt-10">
          <div className="flex items-baseline justify-between gap-3 border-b pb-2">
            <h2 className="text-base font-semibold">Your profile</h2>
            <span className="font-mono text-xs text-muted-foreground">
              {assessed.length} of {assessed.length + skipped.length} criteria assessed
            </span>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-8">
            <ScoreRadar scores={ranked} />
            <div className="min-w-[240px] flex-1">
              {ranked.map((s) => (
                <div
                  key={s.competency_key}
                  className="flex items-center gap-3 border-b py-1.5 last:border-b-0"
                >
                  <span className="min-w-0 flex-1 truncate text-sm">{s.label}</span>
                  <Pips score={s.score} />
                  <span className="w-4 text-right font-mono text-sm tabular-nums">
                    {s.score}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {(report.strengths?.length || report.improvements?.length) && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {report.strengths && report.strengths.length > 0 && (
            <div className="rounded-xl border border-green-200 bg-green-50/60 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-green-800">
                What worked
              </h2>
              <ul className="mt-2.5 flex flex-col gap-2">
                {report.strengths.map((s, i) => (
                  <li key={i} className="text-sm leading-relaxed text-green-900">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.improvements && report.improvements.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-amber-800">
                What to work on
              </h2>
              <ul className="mt-2.5 flex flex-col gap-2">
                {report.improvements.map((s, i) => (
                  <li key={i} className="text-sm leading-relaxed text-amber-900">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Evidence beside the recording rather than below it. The video sticks
          while this column scrolls, so clicking a timecode plays the moment
          without scrolling back up to find the player. */}
      <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div>
      {spoken.length > 0 && (
        <section>
          <div className="flex items-baseline justify-between gap-3 border-b pb-2">
            <h2 className="text-base font-semibold">How you taught</h2>
            <span className="font-mono text-xs text-muted-foreground">
              from the transcript
            </span>
          </div>
          <div className="mt-1">
            {spoken.map((s) => (
              <Criterion
                key={s.competency_key}
                score={s}
                onSeek={report.recording ? seekTo : undefined}
              />
            ))}
          </div>
        </section>
      )}

      <section className="mt-10">
        <div className="flex items-baseline justify-between gap-3 border-b pb-2">
          <h2 className="flex items-center gap-1.5 text-base font-semibold">
            <Video className="h-4 w-4 text-muted-foreground" />
            How you came across
          </h2>
          <span className="font-mono text-xs text-muted-foreground">
            from the recording
          </span>
        </div>
        {delivery.length > 0 ? (
          <div className="mt-1">
            {delivery.map((s) => (
              <Criterion
                key={s.competency_key}
                score={s}
                onSeek={report.recording ? seekTo : undefined}
              />
            ))}
          </div>
        ) : (
          /* Sessions now require a camera to start, so this only appears for
             recordings made before that, or where the video could not be read. */
          <p className="mt-3 rounded-xl border border-dashed p-4 text-sm leading-relaxed text-muted-foreground">
            There was no usable recording for this session, so delivery was not scored.
          </p>
        )}
      </section>
        </div>

        {report.recording && (
          <aside className="lg:sticky lg:top-6 lg:self-start">
            <SessionPlayer ref={videoRef} simulationId={simulationId} />
          </aside>
        )}
      </div>

      {/* Named, not scored. The reasons are stored with the report, so an admin
          reviewing a certification can see what was skipped and why. */}
      {skipped.length > 0 && (
        <p className="mt-8 rounded-xl border border-dashed p-4 text-sm leading-relaxed text-muted-foreground">
          <span className="font-medium text-slate-700">Not assessed in this session:</span>{" "}
          {skipped.map((u) => u.label).join(", ")}. Nothing took place that these could be
          judged on, so they were left unscored rather than given a middling mark.
        </p>
      )}
    </div>
  );
}
