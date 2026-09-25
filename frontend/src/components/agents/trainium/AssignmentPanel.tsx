"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Plus, Trash2, UserPlus } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";

type Assignment = {
  id: string;
  trainer_name: string;
  trainer_email: string;
  code: string;
  code_display: string;
  max_attempts: number;
  attempts_used: number;
  attempts_left: number;
  runs: number;
};

/** Who may deliver this session, and the code that proves it.
 *
 *  Without this an admin has no way to know who actually taught: the link
 *  gets forwarded and a name typed into the green room is whatever the
 *  trainer felt like typing. The code is what a report is filed under.
 */
export function AssignmentPanel({ sessionId }: { sessionId: string }) {
  const [rows, setRows] = useState<Assignment[] | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [attempts, setAttempts] = useState(3);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<Assignment[]>(`/trainium/admin/sessions/${sessionId}/assignments`)
      .then((r) => setRows(r.data))
      .catch(() => setError("Could not load the trainers for this session."));
  }, [sessionId]);

  useEffect(load, [load]);

  async function add() {
    setSaving(true);
    setError(null);
    try {
      const r = await api.post<Assignment>(
        `/trainium/admin/sessions/${sessionId}/assignments`,
        { trainer_name: name.trim(), trainer_email: email.trim(), max_attempts: attempts }
      );
      setRows((prev) => [...(prev ?? []), r.data]);
      setName("");
      setEmail("");
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data
        ?.detail;
      setError(detail || "Could not assign that trainer.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    const previous = rows;
    setRows((prev) => prev?.filter((a) => a.id !== id) ?? null);
    try {
      await api.delete(`/trainium/admin/assignments/${id}`);
    } catch {
      setRows(previous ?? null);
      setError("Could not remove that trainer.");
    }
  }

  async function setAttemptCap(id: string, max: number) {
    const previous = rows;
    setRows(
      (prev) =>
        prev?.map((a) =>
          a.id === id
            ? { ...a, max_attempts: max, attempts_left: Math.max(0, max - a.attempts_used) }
            : a
        ) ?? null
    );
    try {
      await api.patch(`/trainium/admin/assignments/${id}`, { max_attempts: max });
    } catch {
      setRows(previous ?? null);
      setError("Could not change the attempt limit.");
    }
  }

  async function copyInvite(a: Assignment) {
    await navigator.clipboard.writeText(a.code_display);
    setCopied(a.id);
    setTimeout(() => setCopied(null), 2000);
  }

  const canAdd = name.trim().length > 0 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  return (
    <section>
      <h2 className="flex items-center gap-2 text-sm font-medium">
        <UserPlus className="h-4 w-4" />
        Who may deliver this
      </h2>
      <p className="mt-1 max-w-[70ch] text-xs text-muted-foreground">
        Each trainer gets their own code. Send it with the join link. Reports and
        transcripts are filed under the person the code belongs to, not under
        whatever name they type when they arrive. Assign nobody and the link stays
        open to anyone who has it.
      </p>

      {error && <p className="mt-3 text-xs text-destructive">{error}</p>}

      {rows === null ? (
        <p className="mt-3 text-sm text-muted-foreground">Loading...</p>
      ) : (
        <div className="mt-3 space-y-2">
          {rows.map((a) => (
            <div
              key={a.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{a.trainer_name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {a.trainer_email}
                </p>
              </div>

              <code className="shrink-0 rounded bg-slate-100 px-2 py-1 font-mono text-sm tracking-wider">
                {a.code_display}
              </code>

              {/* Used against allowed, rather than only what remains: an admin
                  deciding whether to grant another attempt wants to see how
                  many have already gone. */}
              <div className="shrink-0 text-xs text-muted-foreground">
                <label htmlFor={`cap-${a.id}`} className="sr-only">
                  Attempts allowed for {a.trainer_name}
                </label>
                <span className="tabular-nums">{a.attempts_used} of </span>
                <select
                  id={`cap-${a.id}`}
                  value={a.max_attempts}
                  onChange={(e) => setAttemptCap(a.id, Number(e.target.value))}
                  className="cursor-pointer rounded border bg-background px-1 py-0.5 text-xs"
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                </select>
                <span> attempts used</span>
                {a.attempts_left === 0 && (
                  <span className="ml-1.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
                    none left
                  </span>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                <Button variant="outline" size="sm" onClick={() => copyInvite(a)}>
                  {copied === a.id ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  <span className="ml-1.5">{copied === a.id ? "Copied" : "Code"}</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remove(a.id)}
                  aria-label={`Remove ${a.trainer_name}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-3">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Trainer name"
              aria-label="Trainer name"
              className="min-w-[10rem] flex-1 rounded-md border px-3 py-2 text-sm"
            />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Trainer email"
              aria-label="Trainer email"
              className="min-w-[12rem] flex-1 rounded-md border px-3 py-2 text-sm"
            />
            <label htmlFor="new-attempts" className="text-xs text-muted-foreground">
              Attempts
            </label>
            <select
              id="new-attempts"
              value={attempts}
              onChange={(e) => setAttempts(Number(e.target.value))}
              className="cursor-pointer rounded-md border bg-background px-2 py-2 text-sm"
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
            <Button size="sm" onClick={add} disabled={!canAdd || saving}>
              <Plus className="mr-1.5 h-4 w-4" />
              {saving ? "Assigning..." : "Assign"}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
