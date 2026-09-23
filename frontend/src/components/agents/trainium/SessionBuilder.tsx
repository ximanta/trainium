"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Link2 } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";
import { DeckUpload } from "@/components/agents/trainium/DeckUpload";

type PersonaTemplate = {
  id: string;
  name: string;
  type: string;
  profile: string;
  voice_id: string;
};

type Course = {
  id: string;
  title: string;
  status: string;
};

type Override = {
  display_name?: string;
  profile?: string;
  voice_id?: string;
  speak_probability?: number;
};

// Gemini's prebuilt TTS voices, as mapped to persona types in the
// architecture doc. The admin can reassign any of them per session.
const VOICES = [
  "Puck",
  "Leda",
  "Charon",
  "Vindemiatrix",
  "Despina",
  "Fenrir",
  "Aoede",
  "Orus",
  "Kore",
];

export function SessionBuilder() {
  const [personas, setPersonas] = useState<PersonaTemplate[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [title, setTitle] = useState("");
  const [courseId, setCourseId] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<Record<string, Override>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<PersonaTemplate[]>("/trainium/personas").then((r) => setPersonas(r.data));
    api
      .get<Course[]>("/trainium/admin/courses")
      .then((r) => setCourses(r.data))
      .catch(() => setCourses([]));
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setExpanded((e) => (e === id ? null : e));
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function setOverride(id: string, patch: Override) {
    setOverrides((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      // Only send overrides for personas actually in the session, and only
      // fields the admin filled in, so blanks fall back to the template.
      const cleanOverrides: Record<string, Override> = {};
      for (const id of Array.from(selected)) {
        const o = overrides[id];
        if (!o) continue;
        const entries = Object.entries(o).filter(
          ([, v]) => v !== undefined && v !== "" && v !== null
        );
        if (entries.length) cleanOverrides[id] = Object.fromEntries(entries);
      }

      const created = await api.post("/trainium/admin/sessions", {
        title: title || "Untitled session",
        course_id: courseId || null,
        persona_ids: Array.from(selected),
        persona_overrides: cleanOverrides,
      });
      const published = await api.post(
        `/trainium/admin/sessions/${created.data.id}/publish`
      );
      setJoinUrl(`${window.location.origin}${published.data.join_path}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not publish the session. Is the backend running?"
      );
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!joinUrl) return;
    await navigator.clipboard.writeText(joinUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (joinUrl) {
    return (
      <div className="rounded-lg border bg-card p-6">
        <div className="flex items-center gap-2 text-sm font-medium text-green-700">
          <Check className="h-4 w-4" />
          Session published
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Send this link to the trainer. They land straight in the classroom, with the
          material and learners already set up.
        </p>
        <div className="mt-4 flex items-center gap-2">
          <code className="flex-1 truncate rounded-md bg-muted px-3 py-2 text-sm">
            {joinUrl}
          </code>
          <Button variant="outline" size="sm" onClick={copyLink}>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            <span className="ml-1.5">{copied ? "Copied" : "Copy"}</span>
          </Button>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={() => {
            setJoinUrl(null);
            setSelected(new Set());
            setOverrides({});
            setTitle("");
            setCourseId("");
          }}
        >
          Create another session
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium">Session title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. ReAct Agents, cohort 4"
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
          />
        </label>
        <div>
          <span className="text-sm font-medium">Teaching material</span>
          <select
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            <option value="">No slides</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title} ({c.status})
              </option>
            ))}
          </select>
          <div className="mt-2">
            <DeckUpload
              onUploaded={(course) => {
                setCourses((prev) => [
                  { id: course.id, title: course.title, status: course.status },
                  ...prev.filter((c) => c.id !== course.id),
                ]);
                setCourseId(course.id);
              }}
            />
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium">
          Learners in the room ({selected.size} selected)
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Click to add a learner. Use Customise to change their name, profile, voice or
          how often they speak, for this session only.
        </p>

        <div className="mt-3 space-y-2">
          {personas.map((p) => {
            const isSelected = selected.has(p.id);
            const o = overrides[p.id] ?? {};
            return (
              <div
                key={p.id}
                className={`rounded-lg border ${isSelected ? "border-primary" : ""}`}
              >
                <div className="flex items-center gap-3 p-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggle(p.id)}
                    className="h-4 w-4"
                    aria-label={`Include ${p.name}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">
                      {o.display_name || p.name}{" "}
                      <span className="font-normal text-muted-foreground">
                        · {p.type.replace(/_/g, " ")}
                      </span>
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {o.profile || p.profile}
                    </p>
                  </div>
                  {isSelected && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setExpanded(expanded === p.id ? null : p.id)}
                    >
                      {expanded === p.id ? "Done" : "Customise"}
                    </Button>
                  )}
                </div>

                {isSelected && expanded === p.id && (
                  <div className="grid gap-3 border-t bg-muted/30 p-3 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs font-medium">Display name</span>
                      <input
                        value={o.display_name ?? ""}
                        onChange={(e) => setOverride(p.id, { display_name: e.target.value })}
                        placeholder={p.name}
                        className="mt-1 w-full rounded-md border px-2 py-1.5 text-sm"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs font-medium">Voice</span>
                      <select
                        value={o.voice_id ?? p.voice_id}
                        onChange={(e) => setOverride(p.id, { voice_id: e.target.value })}
                        className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                      >
                        {VOICES.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block sm:col-span-2">
                      <span className="text-xs font-medium">Profile</span>
                      <textarea
                        value={o.profile ?? ""}
                        onChange={(e) => setOverride(p.id, { profile: e.target.value })}
                        placeholder={p.profile}
                        rows={2}
                        className="mt-1 w-full rounded-md border px-2 py-1.5 text-sm"
                      />
                    </label>
                    <label className="block sm:col-span-2">
                      <span className="text-xs font-medium">
                        How often they speak:{" "}
                        {o.speak_probability !== undefined
                          ? `${Math.round(o.speak_probability * 100)}%`
                          : "type default"}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={(o.speak_probability ?? 0.2) * 100}
                        onChange={(e) =>
                          setOverride(p.id, {
                            speak_probability: Number(e.target.value) / 100,
                          })
                        }
                        className="mt-1 w-full"
                      />
                    </label>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button onClick={publish} disabled={busy || selected.size === 0}>
        <Link2 className="mr-1.5 h-4 w-4" />
        {busy ? "Publishing..." : "Publish and get trainer link"}
      </Button>
    </div>
  );
}
