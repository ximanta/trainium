"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Link2, Plus, Users } from "lucide-react";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";
import { DeckUpload } from "@/components/agents/trainium/DeckUpload";
import { PersonaModal, type PersonaDraft } from "@/components/agents/trainium/PersonaModal";
import { formatPersonaType } from "@/components/agents/trainium/personaType";
import type { Voice } from "@/components/agents/trainium/VoicePicker";

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

type TrainerAddress = "sir" | "maam" | "name";

const DEFAULT_SPEAK_PROBABILITY = 0.2;

// A custom learner starts from a blank character rather than a template, so the
// admin writes the behaviour themselves. Ids are client-side only; the backend
// stores them as overrides against the session.
const CUSTOM_PREFIX = "custom_";

function draftFromTemplate(t: PersonaTemplate): PersonaDraft {
  return {
    display_name: t.name,
    profile: t.profile,
    voice_id: t.voice_id,
    speak_probability: DEFAULT_SPEAK_PROBABILITY,
  };
}

export function SessionBuilder() {
  const [personas, setPersonas] = useState<PersonaTemplate[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [title, setTitle] = useState("");
  const [courseId, setCourseId] = useState("");
  const [audience, setAudience] = useState("");
  const [trainerName, setTrainerName] = useState("");
  const [trainerAddress, setTrainerAddress] = useState<TrainerAddress>("name");
  const [durationMin, setDurationMin] = useState(30);
  // Drafts hold the full editable state for everyone in the room, seeded from
  // the template. Presence in this map is what "in the room" means.
  const [room, setRoom] = useState<Record<string, PersonaDraft>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<PersonaTemplate[]>("/trainium/personas").then((r) => setPersonas(r.data));
    api.get<Voice[]>("/trainium/voices").then((r) => setVoices(r.data));
    api
      .get<Course[]>("/trainium/admin/courses")
      .then((r) => setCourses(r.data))
      .catch(() => setCourses([]));
  }, []);

  const [customs, setCustoms] = useState<PersonaTemplate[]>([]);
  const allPersonas = useMemo(() => [...personas, ...customs], [personas, customs]);

  function toggle(id: string) {
    setRoom((prev) => {
      const next = { ...prev };
      if (next[id]) {
        delete next[id];
        return next;
      }
      const template = allPersonas.find((p) => p.id === id);
      if (template) next[id] = draftFromTemplate(template);
      return next;
    });
  }

  function addCustom() {
    if (!voices.length) return;
    const id = `${CUSTOM_PREFIX}${Date.now()}`;
    const template: PersonaTemplate = {
      id,
      name: "New learner",
      type: "custom",
      profile: "",
      voice_id: voices[0].id,
    };
    setCustoms((prev) => [...prev, template]);
    setRoom((prev) => ({ ...prev, [id]: draftFromTemplate(template) }));
    setEditing(id);
  }

  function patchDraft(id: string, patch: Partial<PersonaDraft>) {
    setRoom((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }

  function removeFromRoom(id: string) {
    setRoom((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setCustoms((prev) => prev.filter((p) => p.id !== id));
    setEditing(null);
  }

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const ids = Object.keys(room);
      // Everything in the room is sent as an explicit override. Defaults were
      // loaded from the template and may have been edited, and sending them
      // verbatim is what makes the session reproducible.
      const persona_overrides = Object.fromEntries(
        ids.map((id) => [id, room[id]])
      );

      const created = await api.post("/trainium/admin/sessions", {
        title: title || "Untitled session",
        audience,
        trainer_name: trainerName,
        trainer_address: trainerAddress,
        duration_min: durationMin,
        course_id: courseId || null,
        persona_ids: ids,
        persona_overrides,
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
      <div className="mx-auto max-w-xl rounded-xl border bg-card p-6">
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
            setRoom({});
            setCustoms([]);
            setTitle("");
            setAudience("");
            setCourseId("");
            setTrainerName("");
            setTrainerAddress("name");
            setDurationMin(30);
          }}
        >
          Create another session
        </Button>
      </div>
    );
  }

  const count = Object.keys(room).length;
  const editingTemplate = editing ? allPersonas.find((p) => p.id === editing) : null;

  return (
    <>
      {/* Config left, cast right. The room is the part an admin iterates on, so
          it gets the wider column and stays visible while the form is filled. */}
      <div className="grid gap-8 lg:grid-cols-[20rem_1fr]">
        <div className="space-y-5">
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
            <span className="text-sm font-medium">How long</span>
            <select
              value={durationMin}
              onChange={(e) => setDurationMin(Number(e.target.value))}
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
              aria-label="Session duration"
            >
              {/* Floor of 15: with a 180s per-persona cooldown, a shorter
                  session leaves most of the room silent and reads as broken.
                  Ceiling of 45: the length of a real module, beyond which the
                  Live API reconnections stack up. */}
              {[15, 20, 30, 45].map((m) => (
                <option key={m} value={m}>
                  {m} minutes
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-muted-foreground">
              The session closes itself when the time is up, so an abandoned tab
              cannot keep running.
            </span>
          </div>

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

          <div>
            <span className="text-sm font-medium">Who is the trainer?</span>
            <input
              value={trainerName}
              onChange={(e) => setTrainerName(e.target.value)}
              placeholder="e.g. Anjali Rao"
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
              aria-label="Trainer name"
            />
            <select
              value={trainerAddress}
              onChange={(e) => setTrainerAddress(e.target.value as TrainerAddress)}
              className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm"
              aria-label="How learners address the trainer"
            >
              <option value="name">Address by name</option>
              <option value="maam">Address as Ma&apos;am</option>
              <option value="sir">Address as Sir</option>
            </select>
            <span className="mt-1 block text-xs text-muted-foreground">
              Learners use this when they speak to the trainer. Without it they default
              to no honorific rather than guessing one.
            </span>
          </div>

          <label className="block">
            <span className="text-sm font-medium">Who are the learners?</span>
            <textarea
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              rows={3}
              placeholder="e.g. Fresh engineering graduates from tier-2 Indian colleges, first corporate training"
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              Shapes how the learners talk and what they ask. Leave blank for the default
              cohort of fresh graduates.
            </span>
          </label>

          <div className="rounded-lg border bg-muted/40 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Users className="h-4 w-4 text-muted-foreground" />
              {count} {count === 1 ? "learner" : "learners"} in the room
            </div>
            {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            <Button onClick={publish} disabled={busy || count === 0} className="mt-3 w-full">
              <Link2 className="mr-1.5 h-4 w-4" />
              {busy ? "Publishing..." : "Publish and get link"}
            </Button>
          </div>
        </div>

        <div>
          <h2 className="text-sm font-medium">Learners in the room</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Click a learner to add them. Click again on a selected card to edit their
            name, voice, behaviour and how often they speak, for this session only.
          </p>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {allPersonas.map((p) => {
              const draft = room[p.id];
              const inRoom = Boolean(draft);
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => (inRoom ? setEditing(p.id) : toggle(p.id))}
                  aria-pressed={inRoom}
                  className={`cursor-pointer rounded-lg border p-4 text-left transition-colors ${
                    inRoom
                      ? "border-primary bg-primary/5 hover:bg-primary/10"
                      : "hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium">
                      {draft?.display_name ?? p.name}
                    </p>
                    {inRoom && (
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary">
                        <Check className="h-3 w-3 text-primary-foreground" />
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {formatPersonaType(p.type)}
                  </p>
                  <p className="mt-2 line-clamp-3 text-xs text-muted-foreground">
                    {draft?.profile || p.profile || "No behaviour set yet."}
                  </p>
                  {inRoom && (
                    <span className="mt-2 block text-xs font-medium text-primary">
                      Customise
                    </span>
                  )}
                </button>
              );
            })}

            <button
              type="button"
              onClick={addCustom}
              disabled={!voices.length}
              className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-4 text-center transition-colors hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
            >
              <Plus className="h-5 w-5 text-muted-foreground" />
              <span className="mt-1.5 text-sm font-medium">Add custom learner</span>
              <span className="mt-0.5 text-xs text-muted-foreground">
                Write your own character
              </span>
            </button>
          </div>
        </div>
      </div>

      {editing && editingTemplate && room[editing] && (
        <PersonaModal
          title={room[editing].display_name || editingTemplate.name}
          draft={room[editing]}
          voices={voices}
          onChange={(patch) => patchDraft(editing, patch)}
          onClose={() => setEditing(null)}
          onRemove={() => removeFromRoom(editing)}
        />
      )}
    </>
  );
}
