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
import { formatPersonaType } from "@/components/agents/trainium/personaType";

export type TrainerAddress = "sir" | "maam" | "name";

export type TrainerIdentity = {
  /** Empty for an open session with nobody assigned. */
  code: string;
  /** What the personas call them, which is theirs to choose. */
  displayName: string;
  address: TrainerAddress;
};

/** What a code resolved to. The name and email here are the admin's record,
 *  not anything the trainer typed, and they are what the report is filed
 *  under. */
type VerifiedCode = {
  trainer_name: string;
  trainer_email: string;
  attempts_left: number;
  max_attempts: number;
  exhausted: boolean;
};

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

// The four things that change how a trainer behaves in the room. Each leads
// with what to do, because a heading the trainer can act on is worth more than
// a description of the system.
const BRIEFING = [
  {
    heading: "Just teach. They join in on their own.",
    body: "The learners decide when to speak. You never pick who talks, though you can call on anyone whose hand goes up.",
  },
  {
    heading: "Say “let me explain first” to hold questions",
    body: "That quiets the room until you say “any questions?”. There is also a Hold questions button on the control bar.",
  },
  {
    heading: "Share your screen so they can see it",
    body: "They read what you present and ask about what is actually on it, so questions follow your slides.",
  },
  {
    heading: "Everything is recorded and scored",
    body: "You get a report afterwards where every score cites the moment in the transcript it came from.",
  },
];

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
  requiresCode,
  durationMin,
  personas,
  slides,
  onStart,
}: {
  title: string;
  courseTitle: string;
  audience: string;
  requiresCode: boolean;
  durationMin: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
  onStart: (identity: TrainerIdentity) => void;
}) {
  const [cameraOn, setCameraOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  // Whether a camera track exists at all, as distinct from being switched off.
  const [hasCamera, setHasCamera] = useState(true);
  const [micLevel, setMicLevel] = useState(0);
  // Latches once the mic registers real sound. An enabled mic that has never
  // picked anything up is the silent failure worth warning about, but not
  // worth blocking on: the trainer may simply not have spoken yet.
  const [micProven, setMicProven] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  // Distinct from "a device is on": the permission prompt has been answered
  // either way, so the waiting message can go.
  const [devicesResolved, setDevicesResolved] = useState(false);
  const [slideIndex, setSlideIndex] = useState(0);
  // The code the admin issued, and what it resolved to. Identity is the
  // admin's to assert, not the trainer's: a name typed in here could be
  // anything, so it is kept for the room to use and nothing else.
  const [code, setCode] = useState("");
  const [verified, setVerified] = useState<VerifiedCode | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [address, setAddress] = useState<TrainerAddress>("name");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("trainium.trainer");
      if (!saved) return;
      const parsed = JSON.parse(saved) as {
        name?: string;
        address?: TrainerAddress;
      };
      if (parsed.name) setName(parsed.name);
      if (parsed.address) setAddress(parsed.address);
    } catch {
      // Private windows and blocked storage both throw; the fields just start
      // empty, which is the same as a first visit.
    }
  }, []);

  async function verifyCode() {
    setVerifying(true);
    setCodeError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/trainium/join/verify-code`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setCodeError(body.detail || "That code was not recognised.");
        return;
      }
      const data: VerifiedCode = await res.json();
      setVerified(data);
      // Their real name is the sensible thing to be called, so it is offered
      // rather than imposed. Changing it changes only what the room says.
      if (!name.trim()) setName(data.trainer_name);
    } catch {
      setCodeError("Could not reach the server. Check your connection and try again.");
    } finally {
      setVerifying(false);
    }
  }

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

    // A live level meter, because "the mic is listed" and "the mic is picking
    // up my voice" are different things, and only the second one saves a
    // session. Shared by both paths below so the audio-only fallback is not
    // left with a dead bar.
    function meter(stream: MediaStream) {
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
        const level = Math.min(1, peak / 40);
        setMicLevel(level);
        if (level > 0.12) setMicProven(true);
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    }

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
        setHasCamera(stream.getVideoTracks().length > 0);
        setCameraOn(stream.getVideoTracks().some((t) => t.enabled));
        setMicOn(stream.getAudioTracks().some((t) => t.enabled));
        setDevicesResolved(true);

        meter(stream);
      } catch {
        if (cancelled) return;
        // Both devices are required, so a failure here stops the session. The
        // audio track is still opened, because the mic meter is how a trainer
        // tells a blocked camera from a blocked everything, and because the
        // message should name what is actually wrong.
        try {
          const audioOnly = await navigator.mediaDevices.getUserMedia({ audio: true });
          if (cancelled) {
            audioOnly.getTracks().forEach((t) => t.stop());
            return;
          }
          streamRef.current = audioOnly;
          setHasCamera(false);
          setCameraOn(false);
          setMicOn(true);
          setDevicesResolved(true);
          meter(audioOnly);
          setDeviceError(
            "Could not reach your camera. The session is recorded and scored on how you come across, so a camera is required. Check the browser permission prompt, or that no other app is using it, then reload this page."
          );
        } catch {
          if (!cancelled) {
            setDevicesResolved(true);
            setDeviceError(
              "Could not reach your camera and microphone. Allow access in the browser permission prompt, then reload this page."
            );
          }
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
    if (blocked) return;
    try {
      localStorage.setItem(
        "trainium.trainer",
        JSON.stringify({ name: name.trim(), address })
      );
    } catch {
      // Not being able to remember it is not a reason to block the session.
    }
    stopDevices();
    onStart({ code, displayName: name.trim(), address });
  }

  const slide = slides[slideIndex];
  // Both devices are required. The mic is the session's only input, so without
  // it the personas never hear anything and never respond. The camera is what
  // delivery is scored from, and a report missing half its criteria is not the
  // session the trainer was sent here to have.
  const missingDevices = [!micOn && "microphone", !cameraOn && "camera"].filter(
    Boolean
  ) as string[];
  // A session with trainers assigned admits nobody without a code, since the
  // code is the only thing tying a delivery to a real person. A session with
  // nobody assigned is an open practice link and needs none.
  const identityProblem = !requiresCode
    ? null
    : !verified
      ? "Enter the code from your invitation to start"
      : verified.exhausted
        ? "You have used all your attempts at this session"
        : !name.trim()
          ? "Enter the name you want the learners to use"
          : null;
  const blocked = missingDevices.length > 0 || identityProblem !== null;
  // Identity first: a trainer without a valid code cannot start at all, so
  // telling them to switch a camera on would be advice they cannot act on.
  const blocker =
    identityProblem ?? (missingDevices.length > 0
      ? `Turn your ${missingDevices.join(" and ")} on to start`
      : null);

  return (
    <div className="mx-auto max-w-[88rem]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs tracking-wide text-indigo-700">
            &gt; before you go live
          </p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {name.trim() ? `${name.trim()}, you are` : "You are"} teaching{" "}
            {personas.length} {personas.length === 1 ? "learner" : "learners"}
            {courseTitle ? ` through ${courseTitle}` : ""}. The session runs for{" "}
            {durationMin} minutes and then closes itself.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <Button
            size="lg"
            onClick={start}
            disabled={blocked}
            title={blocker ?? undefined}
          >
            Start the session
          </Button>
          {blocker && (
            <p className="mt-1.5 flex items-center justify-end gap-1 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5" />
              {blocker}
            </p>
          )}
        </div>
      </div>

      {/* Three columns, each a thing the trainer checks before going live:
          their own kit, the deck they will teach, the room they will face.
          The deck takes the middle and the most width because it is what they
          actually spend the time on. */}
      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[19rem_minmax(0,1fr)_16rem]">
        {/* Kit check first: a dead mic is the one failure that wastes the
            whole session, and it is invisible until someone does not respond. */}
        <section>
          {/* The code comes first because nothing else matters until it
              checks out: it decides whether this person may start at all and
              whose report this becomes. */}
          {requiresCode && !verified && (
            <>
              <h2 className="text-sm font-medium">Your trainer code</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                From the invitation you were sent. It identifies you, so your
                report and transcript come back to you and not to whoever else
                has this link.
              </p>
              <form
                className="mt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (code.trim() && !verifying) verifyCode();
                }}
              >
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="TRN-4K2P"
                  aria-label="Your trainer code"
                  autoComplete="off"
                  className="min-w-0 flex-1 rounded-md border px-3 py-2 font-mono text-sm uppercase tracking-wider"
                />
                <Button type="submit" disabled={!code.trim() || verifying}>
                  {verifying ? "Checking..." : "Check"}
                </Button>
              </form>
              {codeError && (
                <p className="mt-1.5 flex gap-1.5 text-xs text-destructive">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {codeError}
                </p>
              )}
            </>
          )}

          {requiresCode && verified && (
            <>
              <h2 className="text-sm font-medium">You are signed in</h2>
              <div className="mt-2 rounded-lg border bg-slate-50 p-3">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <Check className="h-4 w-4 text-green-700" />
                  {verified.trainer_name}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {verified.trainer_email}
                </p>
                {/* Said plainly and up front. Finding out afterwards that a
                    rehearsal was the last one available is the kind of
                    surprise that makes a tool feel hostile. */}
                <p
                  className={`mt-2 text-xs ${
                    verified.exhausted
                      ? "font-medium text-destructive"
                      : verified.attempts_left === 1
                        ? "font-medium text-amber-700"
                        : "text-muted-foreground"
                  }`}
                >
                  {verified.exhausted
                    ? "You have used all your attempts. Ask your administrator to allow another."
                    : `This is attempt ${
                        verified.max_attempts - verified.attempts_left + 1
                      } of ${verified.max_attempts}. Starting the session uses one.`}
                </p>
              </div>
            </>
          )}

          {/* Separate from identity on purpose: what a room calls someone is
              theirs to choose, and it changes nothing about whose delivery
              this is. */}
          <h2 className={`${requiresCode ? "mt-5" : ""} text-sm font-medium`}>
            How should the learners address you?
          </h2>
          <div className="mt-2 flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="What they should call you"
              aria-label="What the learners should call you"
              className="min-w-0 flex-1 rounded-md border px-3 py-2 text-sm"
            />
            <select
              value={address}
              onChange={(e) => setAddress(e.target.value as TrainerAddress)}
              aria-label="How learners address you"
              className="shrink-0 rounded-md border bg-background px-2 py-2 text-sm"
            >
              <option value="name">By name</option>
              <option value="maam">Ma&apos;am</option>
              <option value="sir">Sir</option>
            </select>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {address === "name"
              ? name.trim()
                ? `They will call you ${name.trim()}.`
                : "Leave this blank and they will speak to you without any honorific."
              : `They will call you ${address === "sir" ? "Sir" : "Ma'am"}.`}
          </p>

          <h2 className="mt-5 text-sm font-medium">Check your camera and mic</h2>
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
                  {name.trim() ? initials(name) : "YOU"}
                </span>
              </div>
            )}
          </div>

          <div className="mt-2 flex gap-2">
            {/* Red when off, matching the mic: both now block the session, so
                styling the camera as a soft warning would misrepresent it. */}
            <Button
              variant={cameraOn ? "outline" : "destructive"}
              size="sm"
              onClick={toggleCamera}
              disabled={!hasCamera}
              className="flex-1"
            >
              {cameraOn ? (
                <Video className="mr-1.5 h-4 w-4" />
              ) : (
                <VideoOff className="mr-1.5 h-4 w-4" />
              )}
              {!hasCamera ? "No camera" : cameraOn ? "Camera on" : "Camera off"}
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
            {/* The prompt is an instruction, so it gives way once it has been
                followed. Once the mic has proven itself, the confirmation is
                the only thing left to say. */}
            <div className="flex items-center justify-between text-xs">
              {micProven ? (
                <span className="flex items-center gap-1 font-medium text-green-700">
                  <Check className="h-3 w-3" />
                  Mic is working
                </span>
              ) : (
                <span
                  className={
                    micOn ? "text-muted-foreground" : "font-medium text-destructive"
                  }
                >
                  {micOn
                    ? "Say something to test"
                    : "The learners cannot hear you with the mic off"}
                </span>
              )}
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-green-500 transition-[width] duration-75"
                style={{ width: `${Math.round(micLevel * 100)}%` }}
              />
            </div>
            {micOn && !micProven && (
              <p className="mt-1.5 text-xs text-muted-foreground">
                No sound yet. Speak once to confirm the right microphone is picked up.
              </p>
            )}
          </div>

          {deviceError && (
            <p className="mt-3 flex gap-1.5 text-xs text-destructive">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {deviceError}
            </p>
          )}

          {/* Sits under the camera because that is where the trainer is
              already looking while they test the mic, which is the one moment
              they are idle enough to read. Numbered, not bulleted: these are
              four distinct things to know, and a number invites reading each
              one rather than skimming a list. */}
          <div className="mt-5 rounded-lg border bg-slate-50 p-4">
            <h3 className="text-sm font-semibold">How this runs</h3>
            <ol className="mt-3 space-y-3">
              {BRIEFING.map((item, i) => (
                <li key={item.heading} className="flex gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 font-mono text-[10px] text-white">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-xs font-medium leading-snug">{item.heading}</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                      {item.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* The deck takes the middle: reading through it is the actual
            preparation, so it gets the space and the centre of attention. */}
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
                    className="max-h-[26rem] w-full object-contain"
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

        {/* Who is in the room, with their disposition, so the trainer knows
            what kind of pushback to expect from whom. Scrolls in place: a
            class of twenty must not push the page down. */}
        <section className="flex max-h-[30rem] flex-col">
          <h2 className="text-sm font-medium">
            Who is in the room ({personas.length})
          </h2>
          {audience && (
            <p className="mt-1 text-xs text-muted-foreground">{audience}</p>
          )}
          {/* Name and disposition only. The full character is authoring
              detail the admin wrote; here it is just a roster, and the wall of
              text it made buried the one thing worth scanning. */}
          <div className="mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
            {personas.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-2.5 rounded-lg border px-3 py-2"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-[11px] font-semibold text-white">
                  {initials(p.name)}
                </span>
                <p className="min-w-0 truncate text-sm">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    &middot; {formatPersonaType(p.type)}
                  </span>
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>

      {!devicesResolved && !deviceError && (
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Waiting for camera and microphone permission.
        </p>
      )}
    </div>
  );
}
