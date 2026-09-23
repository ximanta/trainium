"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Play, Square } from "lucide-react";

import { api } from "@/api/axios";

export type Voice = {
  id: string;
  label: string;
  gender: "female" | "male";
  character: string;
  description: string;
};

/** Voice selector with an audio preview.
 *
 *  The preview hits the backend, which speaks a fixed sample line through the
 *  same accent steering a live session uses, so what the admin hears is what
 *  the trainer will hear. Generation takes a few seconds, hence the spinner.
 */
export function VoicePicker({
  voices,
  value,
  onChange,
}: {
  voices: Voice[];
  value: string;
  onChange: (voiceId: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Previews are a few hundred KB each and never change, so a voice is only
  // fetched once per mount however often the admin clicks between them.
  const cacheRef = useRef<Map<string, string>>(new Map());

  const selected = voices.find((v) => v.id === value);

  function stop() {
    audioRef.current?.pause();
    audioRef.current = null;
    setPlaying(false);
  }

  // Switching voice should not leave the previous one talking.
  useEffect(() => stop(), [value]);

  useEffect(() => {
    const cache = cacheRef.current;
    return () => {
      audioRef.current?.pause();
      cache.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  async function preview() {
    if (playing) {
      stop();
      return;
    }
    setError(false);
    let url = cacheRef.current.get(value);
    if (!url) {
      setLoading(true);
      try {
        const res = await api.get(`/trainium/voices/${value}/preview`, {
          responseType: "blob",
        });
        url = URL.createObjectURL(res.data as Blob);
        cacheRef.current.set(value, url);
      } catch {
        setError(true);
        setLoading(false);
        return;
      }
      setLoading(false);
    }
    const audio = new Audio(url);
    audio.onended = () => setPlaying(false);
    audio.onerror = () => {
      setError(true);
      setPlaying(false);
    };
    audioRef.current = audio;
    setPlaying(true);
    void audio.play();
  }

  return (
    <div>
      <div className="flex gap-2">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1.5 text-sm"
          aria-label="Voice"
        >
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label} ({v.gender === "female" ? "female" : "male"})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={preview}
          disabled={loading}
          aria-label={playing ? "Stop preview" : `Play ${selected?.label ?? "voice"} preview`}
          className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-md border transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : playing ? (
            <Square className="h-3.5 w-3.5 fill-current" />
          ) : (
            <Play className="h-4 w-4" />
          )}
        </button>
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">
        {error ? (
          <span className="text-destructive">Could not play the preview. Try again.</span>
        ) : (
          selected?.description
        )}
      </p>
    </div>
  );
}
