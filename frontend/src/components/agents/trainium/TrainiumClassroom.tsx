"use client";

import { useEffect, useRef, useState } from "react";
import { MicVAD } from "@ricky0123/vad-web";
import {
  ChevronLeft,
  ChevronRight,
  Hand,
  Mic,
  MicOff,
  MonitorUp,
  PhoneOff,
  Video,
  VideoOff,
} from "lucide-react";

import { Button } from "@/components/ui/button";

type Participant = {
  personaId: string;
  displayName: string;
  personaType: string;
  avatarUrl: string;
  muted: boolean;
  speaking: boolean;
  handRaised: boolean;
};

type TranscriptLine = {
  speaker: string;
  text: string;
};

type Slide = {
  slide_number: number;
  title: string;
  image_file_id: string;
};

const CHUNK_FRAMES = 1600; // ~100ms at 16kHz, the chunk size Gemini expects

function floatTo16BitPCM(float32: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase();
}

function slideSrc(fileId: string): string {
  return `${process.env.NEXT_PUBLIC_API_URL}/trainium/assets/${fileId}`;
}

// Stable per-persona colour so the same learner always looks the same, the way
// a familiar face would in a real meeting.
const AVATAR_COLORS = [
  "bg-rose-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-teal-500",
  "bg-orange-500",
];

function avatarColor(personaId: string): string {
  let hash = 0;
  for (let i = 0; i < personaId.length; i++) hash = (hash * 31 + personaId.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

/** A camera tile in the filmstrip, following the Teams/Zoom convention: the
 *  video fills the tile, a green border marks the active speaker, and a name
 *  badge with a mute icon sits in the bottom-left corner. */
function VideoTile({
  name,
  personaId,
  avatarUrl,
  speaking,
  muted,
  handRaised,
  onToggleMute,
  children,
}: {
  name: string;
  personaId: string;
  avatarUrl?: string;
  speaking: boolean;
  muted?: boolean;
  handRaised?: boolean;
  onToggleMute?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={`relative aspect-video w-full shrink-0 overflow-hidden rounded-lg bg-slate-800 ${
        speaking ? "ring-2 ring-green-500" : ""
      }`}
    >
      {children ??
        (avatarUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          // Camera-off placeholder, the Teams/Zoom convention: a coloured
          // initials circle centred on the dark tile.
          <div className="flex h-full w-full items-center justify-center bg-slate-800">
            <span
              className={`flex h-12 w-12 items-center justify-center rounded-full text-sm font-semibold text-white ${avatarColor(
                personaId
              )}`}
            >
              {initials(name)}
            </span>
          </div>
        ))}

      {handRaised && (
        <span className="absolute right-1.5 top-1.5 rounded-full bg-amber-400 p-1 shadow">
          <Hand className="h-3.5 w-3.5 text-amber-950" />
        </span>
      )}

      <div className="absolute inset-x-0 bottom-0 flex items-center gap-1 bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5">
        {onToggleMute ? (
          <button
            onClick={onToggleMute}
            className="shrink-0 text-white/90 hover:text-white"
            aria-label={muted ? `Unmute ${name}` : `Mute ${name}`}
            title={muted ? "Unmute" : "Mute"}
          >
            {muted ? (
              <MicOff className="h-3.5 w-3.5 text-red-400" />
            ) : (
              <Mic className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <Mic className="h-3.5 w-3.5 shrink-0 text-white/90" />
        )}
        <span className="truncate text-xs font-medium text-white">{name}</span>
      </div>
    </div>
  );
}

export function TrainiumClassroom({ simulationId }: { simulationId: string }) {
  const [status, setStatus] = useState("Not joined");
  const [joined, setJoined] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [screenSharing, setScreenSharing] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [selfMuted, setSelfMuted] = useState(false);
  const [slides, setSlides] = useState<Slide[]>([]);
  const [slideIndex, setSlideIndex] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const playbackQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const frameCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const slideImgRef = useRef<HTMLImageElement | null>(null);
  // Persona id to display name, kept in a ref so message handlers can resolve
  // names synchronously without waiting on batched state updates.
  const nameByIdRef = useRef<Record<string, string>>({});
  const lastFrameRef = useRef<string | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      vadRef.current?.destroy();
      wsRef.current?.close();
      audioContextRef.current?.close();
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  function updateParticipant(personaId: string, patch: Partial<Participant>) {
    setParticipants((prev) =>
      prev.map((p) => (p.personaId === personaId ? { ...p, ...patch } : p))
    );
  }

  function playChunk(bytes: ArrayBuffer, ctx: AudioContext): Promise<void> {
    const pcm16 = new Int16Array(bytes);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32768;

    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    return new Promise((resolve) => {
      source.onended = () => resolve();
      source.start();
    });
  }

  async function drainPlaybackQueue(ctx: AudioContext) {
    if (isPlayingRef.current) return;
    isPlayingRef.current = true;
    while (playbackQueueRef.current.length > 0) {
      const chunk = playbackQueueRef.current.shift()!;
      await playChunk(chunk, ctx);
    }
    isPlayingRef.current = false;
  }

  async function join() {
    setStatus("Connecting...");
    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000 },
    });

    // Webcam is separate from the mic stream and optional: a trainer without
    // a camera, or who declines the prompt, should still be able to run the
    // session rather than have join() throw.
    try {
      const camStream = await navigator.mediaDevices.getUserMedia({ video: true });
      cameraStreamRef.current = camStream;
      if (cameraVideoRef.current) cameraVideoRef.current.srcObject = camStream;
      setCameraOn(true);
    } catch {
      setCameraOn(false);
    }

    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, "ws")}/trainium/ws/session`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ simulation_id: simulationId }));

    ws.onmessage = async (event) => {
      if (typeof event.data !== "string") return;
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case "roster": {
          const roster: Participant[] = msg.data.personas.map(
            (p: Record<string, unknown>) => ({
              personaId: p.persona_id as string,
              displayName: (p.display_name as string) || (p.persona_id as string),
              personaType: p.persona_type as string,
              avatarUrl: (p.avatar_url as string) || "",
              muted: Boolean(p.muted),
              speaking: false,
              handRaised: false,
            })
          );
          nameByIdRef.current = Object.fromEntries(
            roster.map((p) => [p.personaId, p.displayName])
          );
          setParticipants(roster);
          setSlides((msg.data.slides as Slide[]) ?? []);
          break;
        }
        case "ready":
          setJoined(true);
          setStatus("Listening");
          await startVAD(ws, micStream, audioContext);
          break;
        case "final_transcript":
          setTranscript((prev) => [...prev, { speaker: "You", text: msg.data.text }]);
          break;
        case "hand_raised":
          updateParticipant(msg.data.persona_id, { handRaised: true });
          break;
        case "persona_speaking": {
          // Read the name from a ref, not from state: React batches updates,
          // so a name captured inside a setState updater is not available to
          // the next line, which is what previously left raw ids in the
          // transcript.
          const speakerName =
            nameByIdRef.current[msg.data.persona_id] ?? (msg.data.persona_id as string);
          updateParticipant(msg.data.persona_id, { speaking: true, handRaised: false });
          setTranscript((prev) => [...prev, { speaker: speakerName, text: msg.data.text }]);
          break;
        }
        case "persona_audio":
          playbackQueueRef.current.push(base64ToArrayBuffer(msg.data.b64));
          drainPlaybackQueue(audioContext);
          break;
        case "persona_done":
          setParticipants((prev) => prev.map((p) => ({ ...p, speaking: false })));
          break;
        case "persona_muted":
          updateParticipant(msg.data.persona_id, { muted: msg.data.muted });
          break;
        case "barge_in_ack":
          playbackQueueRef.current = [];
          break;
        case "error":
          setStatus(`Error: ${msg.data.message}`);
          break;
      }
    };

    ws.onclose = () => {
      setJoined(false);
      setStatus("Disconnected");
    };
    ws.onerror = () => setStatus("Connection error");
  }

  // Grab the shared screen as a small JPEG. Downscaled to 1024px wide at
  // quality 0.6, which lands around 10KB and costs no measurable latency in
  // the Director call, while staying legible enough to read slide text.
  function captureScreenFrame(): string | null {
    // Capture whatever is actually on the stage. Screen share wins when
    // active, otherwise the current slide. Reading only the screen-share
    // element meant personas saw a blank frame during a slide-driven
    // session.
    const source: HTMLVideoElement | HTMLImageElement | null = screenSharing
      ? screenVideoRef.current
      : slideImgRef.current;
    if (!source) return null;

    const srcWidth =
      source instanceof HTMLVideoElement ? source.videoWidth : source.naturalWidth;
    const srcHeight =
      source instanceof HTMLVideoElement ? source.videoHeight : source.naturalHeight;
    if (!srcWidth || !srcHeight) return null;

    const width = 1024;
    const height = Math.round((srcHeight / srcWidth) * width);
    const canvas = frameCanvasRef.current ?? document.createElement("canvas");
    frameCanvasRef.current = canvas;
    canvas.width = width;
    canvas.height = height;
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return null;
    try {
      ctx2d.drawImage(source, 0, 0, width, height);
      return canvas.toDataURL("image/jpeg", 0.6).split(",")[1];
    } catch {
      // A cross-origin image taints the canvas and makes toDataURL throw.
      // Better to send nothing than to break the turn.
      return null;
    }
  }

  function sendScreenFrameIfChanged(ws: WebSocket) {
    const b64 = captureScreenFrame();
    if (!b64) return;
    // Only resend when the screen actually changed. Re-sending an identical
    // frame every turn would burn tokens for no new information.
    if (b64 === lastFrameRef.current) return;
    lastFrameRef.current = b64;
    ws.send(JSON.stringify({ type: "screen_frame", data: { b64 } }));
  }

  async function startVAD(ws: WebSocket, micStream: MediaStream, ctx: AudioContext) {
    const source = ctx.createMediaStreamSource(micStream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    const silentGain = ctx.createGain();
    silentGain.gain.value = 0;
    processor.connect(silentGain);
    silentGain.connect(ctx.destination);

    let speaking = false;

    const vad = await MicVAD.new({
      workletURL: "/vad/vad.worklet.bundle.min.js",
      modelURL: "/vad/silero_vad.onnx",
      ortConfig: (ort) => {
        ort.env.wasm.wasmPaths = "/vad/";
      },
      onSpeechStart: () => {
        speaking = true;
        setStatus("You are speaking");
        // Capture what is on screen as the turn begins, so the Director sees
        // the slide or demo the trainer is actually talking over.
        sendScreenFrameIfChanged(ws);
        ws.send(JSON.stringify({ type: "activity_start" }));
      },
      onSpeechEnd: () => {
        speaking = false;
        setStatus("Listening");
        ws.send(JSON.stringify({ type: "activity_end" }));
      },
    });
    vad.start();
    vadRef.current = vad;

    processor.onaudioprocess = (e) => {
      if (!speaking || ws.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      for (let offset = 0; offset < input.length; offset += CHUNK_FRAMES) {
        const slice = input.subarray(offset, Math.min(offset + CHUNK_FRAMES, input.length));
        ws.send(floatTo16BitPCM(slice));
      }
    };
  }

  function send(type: string, data: Record<string, unknown> = {}) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }));
    }
  }

  function stopSharing() {
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    screenStreamRef.current = null;
    lastFrameRef.current = null;
    setScreenSharing(false);
    send("screen_share", { on: false });
  }

  async function toggleScreenShare() {
    if (screenSharing) {
      stopSharing();
      return;
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    screenStreamRef.current = stream;
    if (screenVideoRef.current) screenVideoRef.current.srcObject = stream;
    // The browser's own "stop sharing" control bypasses our button, so listen
    // for the track ending too or the UI would show sharing forever.
    stream.getVideoTracks()[0].addEventListener("ended", stopSharing);
    setScreenSharing(true);
    send("screen_share", { on: true });
  }

  function toggleCamera() {
    const track = cameraStreamRef.current?.getVideoTracks()[0];
    if (!track) return;
    track.enabled = !track.enabled;
    setCameraOn(track.enabled);
  }

  function toggleSelfMute() {
    // Pausing VAD stops both the turn signalling and the audio chunks, which
    // is what "mute" means here: the classroom stops hearing the trainer.
    if (selfMuted) {
      vadRef.current?.start();
      setSelfMuted(false);
      setStatus("Listening");
    } else {
      vadRef.current?.pause();
      setSelfMuted(true);
      setStatus("You are muted");
    }
  }

  function leave() {
    vadRef.current?.destroy();
    wsRef.current?.close();
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
    setJoined(false);
    setStatus("Left the session");
  }

  const raisedHands = participants.filter((p) => p.handRaised);
  const speakingNow = participants.find((p) => p.speaking);
  const currentSlide = slides[slideIndex];

  function goToSlide(index: number) {
    if (index < 0 || index >= slides.length) return;
    setSlideIndex(index);
    // Tell the Director which slide is up, so personas can ask about the
    // material actually on screen.
    send("slide_change", { slide: slides[index].slide_number });
    // Push the new slide image too, otherwise the Director keeps reasoning
    // about the previous slide until the trainer happens to speak again.
    // Waiting a tick lets the img element swap to the new src first.
    const ws = wsRef.current;
    if (ws) setTimeout(() => sendScreenFrameIfChanged(ws), 300);
  }

  return (
    <div className="flex h-[calc(100vh-6rem)] gap-3">
      {/* Participant rail: vertical and scrollable so a class of twenty fits
          without squeezing the slide. Mirrors the Teams sidebar rather than a
          horizontal filmstrip, which runs out of width fast. */}
      <aside className="flex w-52 shrink-0 flex-col rounded-xl border bg-card">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <h2 className="text-xs font-semibold">People ({participants.length + 1})</h2>
          {raisedHands.length > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
              <Hand className="h-3 w-3" />
              {raisedHands.length}
            </span>
          )}
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-2">
          <VideoTile name="You" personaId="trainer" speaking={false} muted={selfMuted}>
            <>
              <video
                ref={cameraVideoRef}
                autoPlay
                muted
                playsInline
                className={cameraOn ? "h-full w-full object-cover" : "hidden"}
              />
              {!cameraOn && (
                <div className="flex h-full w-full items-center justify-center bg-slate-800">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-600 text-sm font-semibold text-white">
                    YOU
                  </span>
                </div>
              )}
            </>
          </VideoTile>

          {participants.map((p) => (
            <div key={p.personaId}>
              <VideoTile
                name={p.displayName}
                personaId={p.personaId}
                avatarUrl={p.avatarUrl}
                speaking={p.speaking}
                muted={p.muted}
                handRaised={p.handRaised}
                onToggleMute={
                  joined
                    ? () => send("set_muted", { persona_id: p.personaId, muted: !p.muted })
                    : undefined
                }
              />
              {p.handRaised && (
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-1 h-7 w-full text-xs"
                  onClick={() => send("raise_hand_ack", { persona_id: p.personaId })}
                >
                  Call on {p.displayName}
                </Button>
              )}
            </div>
          ))}
        </div>
      </aside>

      {/* Stage */}
      <section className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-xl bg-slate-900">
          <video
            ref={screenVideoRef}
            autoPlay
            muted
            playsInline
            className={screenSharing ? "h-full w-full object-contain" : "hidden"}
          />

          {!screenSharing && currentSlide && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              ref={slideImgRef}
              crossOrigin="anonymous"
              src={slideSrc(currentSlide.image_file_id)}
              alt={currentSlide.title || "Slide " + currentSlide.slide_number}
              className="h-full w-full object-contain"
            />
          )}

          {!screenSharing && !currentSlide && (
            <div className="px-6 text-center">
              <p className="text-sm text-slate-300">Nothing is being presented</p>
              <p className="mt-1 text-xs text-slate-500">
                Share your screen, or ask your admin to attach teaching material to this
                session.
              </p>
            </div>
          )}

          {speakingNow && (
            <div className="absolute bottom-3 left-3 flex items-center gap-2 rounded-full bg-black/70 px-3 py-1.5 text-white backdrop-blur">
              <span className="flex h-2 w-2 rounded-full bg-green-500" />
              <span className="text-xs font-medium">
                {speakingNow.displayName} is speaking
              </span>
            </div>
          )}

          {!screenSharing && slides.length > 0 && (
            <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-black/70 px-2 py-1 text-white backdrop-blur">
              <button
                onClick={() => goToSlide(slideIndex - 1)}
                disabled={slideIndex === 0}
                className="rounded p-1 hover:bg-white/10 disabled:opacity-30"
                aria-label="Previous slide"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="px-1 text-xs tabular-nums">
                {slideIndex + 1} / {slides.length}
              </span>
              <button
                onClick={() => goToSlide(slideIndex + 1)}
                disabled={slideIndex >= slides.length - 1}
                className="rounded p-1 hover:bg-white/10 disabled:opacity-30"
                aria-label="Next slide"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        {/* Control bar */}
        <div className="flex items-center justify-center gap-2 rounded-xl border bg-card px-4 py-2">
          {!joined ? (
            <Button onClick={join}>Join session</Button>
          ) : (
            <>
              <Button
                variant={selfMuted ? "destructive" : "outline"}
                size="sm"
                onClick={toggleSelfMute}
              >
                {selfMuted ? (
                  <MicOff className="mr-1.5 h-4 w-4" />
                ) : (
                  <Mic className="mr-1.5 h-4 w-4" />
                )}
                {selfMuted ? "Unmute" : "Mute"}
              </Button>
              <Button
                variant={cameraOn ? "outline" : "destructive"}
                size="sm"
                onClick={toggleCamera}
              >
                {cameraOn ? (
                  <Video className="mr-1.5 h-4 w-4" />
                ) : (
                  <VideoOff className="mr-1.5 h-4 w-4" />
                )}
                {cameraOn ? "Camera on" : "Camera off"}
              </Button>
              <Button variant="outline" size="sm" onClick={toggleScreenShare}>
                <MonitorUp className="mr-1.5 h-4 w-4" />
                {screenSharing ? "Stop sharing" : "Share"}
              </Button>
              <Button variant="destructive" size="sm" onClick={leave}>
                <PhoneOff className="mr-1.5 h-4 w-4" />
                Leave
              </Button>
            </>
          )}
          <span className="ml-3 text-xs text-muted-foreground">{status}</span>
        </div>
      </section>

      {/* Transcript */}
      <aside className="flex w-72 shrink-0 flex-col rounded-xl border bg-card">
        <div className="border-b px-4 py-2">
          <h2 className="text-xs font-semibold">Transcript</h2>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
          {transcript.length === 0 && (
            <p className="text-xs text-muted-foreground">
              The conversation will appear here.
            </p>
          )}
          {transcript.map((line, i) => (
            <div key={i}>
              <p className="text-xs font-medium text-muted-foreground">{line.speaker}</p>
              <p className="text-sm">{line.text}</p>
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>
      </aside>
    </div>
  );
}
