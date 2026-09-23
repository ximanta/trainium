"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { VoicePicker, type Voice } from "@/components/agents/trainium/VoicePicker";

export type PersonaDraft = {
  display_name: string;
  profile: string;
  voice_id: string;
  speak_probability: number;
};

/** Editor for one learner, in a dialog rather than inline.
 *
 *  Fields hold real values, never placeholders: the profile is the persona's
 *  character as the Director receives it, so an admin has to be able to read
 *  and edit what will actually be sent.
 */
export function PersonaModal({
  title,
  draft,
  voices,
  onChange,
  onClose,
  onRemove,
}: {
  title: string;
  draft: PersonaDraft;
  voices: Voice[];
  onChange: (patch: Partial<PersonaDraft>) => void;
  onClose: () => void;
  onRemove?: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // The page behind must not scroll while the dialog is open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLInputElement>("input, textarea")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Edit ${title}`}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white shadow-xl"
      >
        <div className="sticky top-0 flex items-center justify-between border-b bg-white px-5 py-3.5">
          <h2 className="font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="cursor-pointer rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <label className="block">
            <span className="text-sm font-medium">Name</span>
            <input
              value={draft.display_name}
              onChange={(e) => onChange({ display_name: e.target.value })}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>

          <div>
            <span className="text-sm font-medium">Voice</span>
            <div className="mt-1">
              <VoicePicker
                voices={voices}
                value={draft.voice_id}
                onChange={(voice_id) => onChange({ voice_id })}
              />
            </div>
          </div>

          <label className="block">
            <span className="text-sm font-medium">How they behave</span>
            <textarea
              value={draft.profile}
              onChange={(e) => onChange({ profile: e.target.value })}
              rows={7}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm leading-relaxed"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              This is the character the learner is given. Say how they speak, what they
              tend to ask about, and how formal their English is. The more specific it
              is, the less generic they sound.
            </span>
          </label>

          <label className="block">
            <span className="text-sm font-medium">
              How often they speak: {Math.round(draft.speak_probability * 100)}%
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={draft.speak_probability * 100}
              onChange={(e) =>
                onChange({ speak_probability: Number(e.target.value) / 100 })
              }
              className="mt-2 w-full cursor-pointer"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              How likely they are to take a turn when the Director offers one.
            </span>
          </label>
        </div>

        <div className="sticky bottom-0 flex items-center justify-between border-t bg-white px-5 py-3">
          {onRemove ? (
            <Button variant="ghost" size="sm" onClick={onRemove} className="text-destructive">
              Remove from room
            </Button>
          ) : (
            <span />
          )}
          <Button size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
