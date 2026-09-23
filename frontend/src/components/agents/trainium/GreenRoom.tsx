"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Mic,
  MicOff,
  Video,
  VideoOff,
} from "lucide-react";

import { Button } from "@/components/ui/button";

export type GreenRoomPersona = {
  id: string;
  name: string;
  type: string;
  profile: string;
};

export type GreenRoomSlide = {
  slide_number: number;
  title: string;
  image_file_id: string;
};

function slideSrc(fileId: string): string {
  return `${process.env.NEXT_PUBLIC_API_URL}/trainium/assets/${fileId}`;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** What the trainer does before going live: confirm their camera and mic work,
 *  see who is in the room, and read through the deck they are about to teach.
 *
 *  Separate from the classroom because the classroom's panels are all about a
 *  session in progress. Showing them empty, with a presentation stage reading
 *  "nothing is being presented", tells the trainer nothing and looks broken.
 */
export function GreenRoom({
  title,
  courseTitle,
  audience,
  trainerName,
  durationMin,
  personas,
  slides,
  onStart,
}: {
  title: string;
  courseTitle: string;
  audience: string;
  trainerName: string;
  durationMin: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
  onStart: () => void;
}) {
  const [cameraOn, setCameraOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [slideIndex, setSlideIndex] = useState(0);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  const stopDevices = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  // The green room holds its own camera and mic so the trainer can see and hear
  // themselves before anyone else does. Released on start, so the classroom
  // opens its own and two components never hold the same device.
  useEffect(() => {
    let cancelled = false;

    async function openDevices() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setCameraOn(stream.getVideoTracks().some((t) => t.enabled));
        setMicOn(stream.getAudioTracks().some((t) => t.enabled));

        // A live level meter, because "the mic is listed" and "the mic is
        // picking up my voice" are different things, and only the second one
        // saves a session.
        const ctx = new AudioContext();
        audioCtxRef.current = ctx;
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);

        const tick = () => {
          analyser.getByteTimeDomainData(data);
          let peak = 0;
          for (let i = 0; i < data.length; i++) {
            peak = Math.max(peak, Math.abs(data[i] - 128));
          }
          setMicLevel(Math.min(1, peak / 40));
          rafRef.current = requestAnimationFrame(tick);
        };
        tick();
      } catch {
        if (!cancelled) {
          setDeviceError(
            "Could not reach your camera or microphone. Check the browser permission prompt, then reload."
          );
        }
      }
    }

    openDevices();
    return () => {
      cancelled = true;
      stopDevices();
    };
  }, [stopDevices]);

  function toggleCamera() {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setCameraOn(track.enabled);
  }

  function toggleMic() {
    const track = streamRef.current?.getAudioTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setMicOn(track.enabled);
  }

  function start() {
    stopDevices();
    onStart();
  }

  const slide = slides[slideIndex];
  const ready = cameraOn || micOn;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-wide text-indigo-700">
            &gt; before you go live
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {trainerName ? `${trainerName}, you are` : "You are"} teaching{" "}
            {personas.length} {personas.length === 1 ? "learner" : "learners"}
            {courseTitle ? ` through ${courseTitle}` : ""}. Planned for about{" "}
            {durationMin} minutes.
          </p>
        </div>
        <Button size="lg" onClick={start} className="shrink-0">
          Start the session
        </Button>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[22rem_1fr]">
        {/* Kit check first: a dead mic is the one failure that wastes the
            whole session, and it is invisible until someone does not respond. */}
        <section>
          <h2 className="text-sm font-medium">Check your camera and mic</h2>
          <div className="relative mt-2 aspect-video overflow-hidden rounded-xl bg-slate-900">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className={cameraOn ? "h-full w-full object-cover" : "hidden"}
            />
            {!cameraOn && (
              <div className="flex h-full w-full items-center justify-center">
                <span className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-700 text-lg font-semibold text-white">
                  {trainerName ? initials(trainerName) : "YOU"}
                </span>
              </div>
            )}
          </div>

          <div className="mt-2 flex gap-2">
            <Button
              variant={cameraOn ? "outline" : "destructive"}
              size="sm"
              onClick={toggleCamera}
              className="flex-1"
            >
              {cameraOn ? (
                <Video className="mr-1.5 h-4 w-4" />
              ) : (
                <VideoOff className="mr-1.5 h-4 w-4" />
              )}
              {cameraOn ? "Camera on" : "Camera off"}
            </Button>
            <Button
              variant={micOn ? "outline" : "destructive"}
              size="sm"
              onClick={toggleMic}
              className="flex-1"
            >
              {micOn ? (
                <Mic className="mr-1.5 h-4 w-4" />
              ) : (
                <MicOff className="mr-1.5 h-4 w-4" />
              )}
              {micOn ? "Mic on" : "Mic off"}
            </Button>
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Say something to test</span>
              {micLevel > 0.12 && (
                <span className="flex items-center gap-1 font-medium text-green-700">
                  <Check className="h-3 w-3" />
                  hearing you
                </span>
              )}
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-green-500 transition-[width] duration-75"
                style={{ width: `${Math.round(micLevel * 100)}%` }}
              />
            </div>
          </div>

          {deviceError && (
            <p className="mt-3 flex gap-1.5 text-xs text-destructive">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {deviceError}
            </p>
          )}

          <div className="mt-5 rounded-lg border bg-muted/40 p-4">
            <h3 className="text-sm font-medium">How this runs</h3>
            <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground">
              <li>
                The learners listen and speak on their own. You do not call on them
                unless a hand goes up.
              </li>
              <li>
                Say &quot;let me explain first&quot; to hold their questions, and
                &quot;any questions?&quot; to open the floor again.
              </li>
              <li>
                Share your screen so they can see and react to what you are showing.
              </li>
              <li>The session is recorded and scored afterwards against the rubric.</li>
            </ul>
          </div>
        </section>

        <div className="space-y-5">
          {/* Who is in the room, with their disposition, so the trainer knows
              what kind of pushback to expect from whom. */}
          <section>
            <h2 className="text-sm font-medium">
              Who is in the room ({personas.length})
            </h2>
            {audience && (
              <p className="mt-1 text-xs text-muted-foreground">{audience}</p>
            )}
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {personas.map((p) => (
                <div key={p.id} className="flex gap-3 rounded-lg border p-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white">
                    {initials(p.name)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{p.name}</p>
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {p.type.replace(/_/g, " ")}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {p.profile}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* The actual deck. Reading it here is the preparation, so it is
              browsable rather than a count. */}
          <section>
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium">
                Your material {slides.length > 0 && `(${slides.length} slides)`}
              </h2>
              {slide?.title && (
                <span className="truncate pl-3 text-xs text-muted-foreground">
                  {slide.title}
                </span>
              )}
            </div>

            {slides.length === 0 ? (
              <div className="mt-2 rounded-lg border border-dashed p-6 text-center">
                <p className="text-sm font-medium">No slides for this session</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  You can still teach and share your screen. The learners react to
                  whatever you show them.
                </p>
              </div>
            ) : (
              <>
                <div className="relative mt-2 overflow-hidden rounded-lg border bg-slate-900">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={slideSrc(slide.image_file_id)}
                    alt={slide.title || `Slide ${slide.slide_number}`}
                    className="max-h-[22rem] w-full object-contain"
                  />
                  <div className="absolute bottom-2 right-2 flex items-center gap-1 rounded-full bg-black/70 px-2 py-1 text-white backdrop-blur">
                    <button
                      type="button"
                      onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
                      disabled={slideIndex === 0}
                      aria-label="Previous slide"
                      className="cursor-pointer rounded p-1 hover:bg-white/10 disabled:opacity-30"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <span className="px-1 text-xs tabular-nums">
                      {slideIndex + 1} / {slides.length}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setSlideIndex((i) => Math.min(slides.length - 1, i + 1))
                      }
                      disabled={slideIndex >= slides.length - 1}
                      aria-label="Next slide"
                      className="cursor-pointer rounded p-1 hover:bg-white/10 disabled:opacity-30"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                  {slides.map((s, i) => (
                    <button
                      key={s.slide_number}
                      type="button"
                      onClick={() => setSlideIndex(i)}
                      aria-label={`Go to slide ${s.slide_number}`}
                      aria-current={i === slideIndex}
                      className={`shrink-0 cursor-pointer overflow-hidden rounded border-2 transition-colors ${
                        i === slideIndex
                          ? "border-primary"
                          : "border-transparent hover:border-slate-300"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={slideSrc(s.image_file_id)}
                        alt=""
                        loading="lazy"
                        className="h-14 w-24 bg-slate-900 object-contain"
                      />
                    </button>
                  ))}
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      {!ready && !deviceError && (
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Waiting for camera and microphone permission.
        </p>
      )}
    </div>
  );
}
