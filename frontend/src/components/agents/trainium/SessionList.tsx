"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, Plus, Trash2, Users } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";

type SessionRow = {
  id: string;
  title: string;
  status: string;
  join_token?: string;
  persona_ids: string[];
  duration_min: number;
  created_at?: string;
  trainer_name?: string;
  actual_duration_s?: number;
};

function formatDate(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

/** Every session the admin has created, so a published link can be found
 *  again. Without this the join link only ever existed on the screen that
 *  created it, and closing the tab lost it for good.
 */
export function SessionList() {
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<SessionRow[]>("/trainium/admin/sessions")
      .then((r) => setSessions(r.data))
      .catch(() => setError("Could not load sessions. Is the backend running?"));
  }, []);

  async function copyLink(s: SessionRow) {
    if (!s.join_token) return;
    await navigator.clipboard.writeText(
      `${window.location.origin}/trainium/join/${s.join_token}`
    );
    setCopiedId(s.id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function remove(id: string) {
    // Optimistic: the row goes immediately and comes back only if the
    // delete actually failed, which keeps a confirmed action feeling done.
    const previous = sessions;
    setSessions((prev) => prev?.filter((s) => s.id !== id) ?? null);
    setConfirming(null);
    try {
      await api.delete(`/trainium/admin/sessions/${id}`);
    } catch {
      setSessions(previous ?? null);
      setError("Could not delete that session.");
    }
  }

  if (error && !sessions) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  if (sessions === null) {
    return <p className="text-sm text-muted-foreground">Loading sessions...</p>;
  }

  if (sessions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center">
        <p className="text-sm font-medium">No sessions yet</p>
        <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">
          Set one up, then send the link to your trainer. They land straight in the
          classroom with the material and learners already configured.
        </p>
        <Button asChild size="sm" className="mt-4">
          <Link href="/trainium/admin/new">
            <Plus className="mr-1.5 h-4 w-4" />
            Set up a session
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {sessions.map((s) => (
        <div
          key={s.id}
          className="flex flex-wrap items-center gap-3 rounded-lg border p-3"
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="truncate text-sm font-medium">{s.title || "Untitled"}</p>
              {s.status === "complete" && (
                <span className="shrink-0 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-800">
                  run
                </span>
              )}
              {!s.join_token && (
                <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                  draft
                </span>
              )}
            </div>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Users className="h-3 w-3" />
                {s.persona_ids?.length ?? 0}
              </span>
              <span>{s.duration_min} min</span>
              {s.created_at && <span>{formatDate(s.created_at)}</span>}
              {s.trainer_name && <span>taught by {s.trainer_name}</span>}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            {s.join_token && (
              <Button variant="outline" size="sm" onClick={() => copyLink(s)}>
                {copiedId === s.id ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                <span className="ml-1.5">{copiedId === s.id ? "Copied" : "Link"}</span>
              </Button>
            )}
            {s.status === "complete" && (
              <Button asChild variant="outline" size="sm">
                <Link href={`/trainium/report/${s.id}`}>Report</Link>
              </Button>
            )}
            <Button asChild variant="outline" size="sm">
              <Link href={`/trainium/admin/${s.id}`}>Edit</Link>
            </Button>
            {confirming === s.id ? (
              <>
                <Button variant="destructive" size="sm" onClick={() => remove(s.id)}>
                  Delete
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(s.id)}
                aria-label={`Delete ${s.title || "session"}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
