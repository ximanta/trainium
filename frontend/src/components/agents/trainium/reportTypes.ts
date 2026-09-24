export type Evidence = {
  competency_key: string;
  quote: string;
  ts_start: number;
  ts_end: number;
  speaker: string;
  source: "transcript" | "video";
  positive: boolean;
};

export type Score = {
  competency_key: string;
  label: string;
  score: number;
  rationale: string;
  evidence: Evidence[];
};

/** A criterion the session gave no basis to judge. Shown only as a closing
 *  note, never as a score, so an absence cannot be mistaken for a middling
 *  result. The reason is kept for traceability. */
export type Undetermined = {
  competency_key: string;
  label: string;
  reason: string;
  source: "transcript" | "video";
};

/** Session details, returned alongside the report so the trainer can head the
 *  document without reaching an admin-only route. */
export type ReportSession = {
  title?: string;
  trainer_name?: string;
  duration_min?: number;
  persona_ids?: string[];
};

/** Present only when a camera track was stored for the session. */
export type ReportRecording = {
  duration_s?: number;
  size_bytes?: number;
};

/** How much of the deck the session reached. Measured, not scored: quality
 *  and coverage are independent, so they are reported as separate facts. */
export type ReportCoverage = {
  slides_total: number;
  furthest_slide: number;
  slides_discussed: number;
  fraction: number;
  met_threshold: boolean;
  elapsed_min: number;
  planned_min: number;
};

export type Report = {
  session?: ReportSession;
  recording?: ReportRecording | null;
  coverage?: ReportCoverage | null;
  status: "pending" | "running" | "complete" | "failed";
  error?: string;
  summary?: string;
  strengths?: string[];
  improvements?: string[];
  scores?: Score[];
  video_scores?: Score[];
  undetermined?: Undetermined[];
  video_analysed?: boolean;
  created_at?: string;
};
