"use client";

import { useEffect, useRef, useState } from "react";
import { MicVAD } from "@ricky0123/vad-web";
import { Hand, Mic, MicOff, MonitorUp, PhoneOff } from "lucide-react";

import { Button } from "@/components/ui/button";

type Participant = {
  personaId: string;
  displayName: string;
  personaType: string;
  muted: boolean;
  speaking: boolean;
  handRaised: boolean;
};

type TranscriptLine = {
  speaker: string;
  text: string;
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

export function TrainiumClassroom({ simulationId }: { simulationId: string }) {
  const [status, setStatus] = useState("Not joined");
  const [joined, setJoined] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [screenSharing, setScreenSharing] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const playbackQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      vadRef.current?.destroy();
      wsRef.current?.close();
      audioContextRef.current?.close();
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
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
        case "roster":
          setParticipants(
            msg.data.personas.map((p: Record<string, unknown>) => ({
              personaId: p.persona_id as string,
              displayName: (p.display_name as string) || (p.persona_id as string),
              personaType: p.persona_type as string,
              muted: Boolean(p.muted),
              speaking: false,
              handRaised: false,
            }))
          );
          break;
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
        case "persona_speaking":
          updateParticipant(msg.data.persona_id, { speaking: true, handRaised: false });
          setTranscript((prev) => [
            ...prev,
            { speaker: msg.data.persona_id, text: msg.data.text },
          ]);
          break;
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

  async function toggleScreenShare() {
    if (screenSharing) {
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current = null;
      setScreenSharing(false);
      send("screen_share", { on: false });
      return;
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    screenStreamRef.current = stream;
    if (screenVideoRef.current) screenVideoRef.current.srcObject = stream;
    // The browser's own "stop sharing" control bypasses our button, so listen
    // for the track ending too or the UI would show sharing forever.
    stream.getVideoTracks()[0].addEventListener("ended", () => {
      setScreenSharing(false);
      send("screen_share", { on: false });
    });
    setScreenSharing(true);
    send("screen_share", { on: true });
  }

  function leave() {
    vadRef.current?.destroy();
    wsRef.current?.close();
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    setJoined(false);
    setStatus("Left the session");
  }

  const raisedHands = participants.filter((p) => p.handRaised);

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Participants sidebar */}
      <aside className="flex w-64 shrink-0 flex-col rounded-lg border bg-card">
        <div className="border-b px-4 py-3">
          <h2 className="text-sm font-semibold">
            Participants ({participants.length + 1})
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <div className="flex items-center gap-3 rounded-md px-2 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              YOU
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">You (trainer)</p>
            </div>
          </div>

          {participants.map((p) => (
            <div
              key={p.personaId}
              className={`flex items-center gap-3 rounded-md px-2 py-2 ${
                p.speaking ? "bg-primary/10" : ""
              }`}
            >
              <div
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  p.speaking
                    ? "bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {initials(p.displayName)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{p.displayName}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {p.personaType.replace(/_/g, " ")}
                </p>
              </div>
              {p.handRaised && (
                <Hand className="h-4 w-4 shrink-0 text-amber-500" aria-label="Hand raised" />
              )}
              <button
                onClick={() => send("set_muted", { persona_id: p.personaId, muted: !p.muted })}
                disabled={!joined}
                className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-40"
                aria-label={p.muted ? `Unmute ${p.displayName}` : `Mute ${p.displayName}`}
                title={p.muted ? "Unmute" : "Mute"}
              >
                {p.muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Stage */}
      <section className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="relative flex flex-1 items-center justify-center overflow-hidden rounded-lg border bg-muted/30">
          <video
            ref={screenVideoRef}
            autoPlay
            muted
            playsInline
            className={screenSharing ? "h-full w-full object-contain" : "hidden"}
          />
          {!screenSharing && (
            <p className="px-6 text-center text-sm text-muted-foreground">
              Share your screen to present. Course slides will appear here once the
              session is configured with teaching material.
            </p>
          )}
        </div>

        {raisedHands.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
            <p className="mb-2 text-xs font-medium text-amber-900">
              Waiting to speak
            </p>
            <div className="flex flex-wrap gap-2">
              {raisedHands.map((p) => (
                <Button
                  key={p.personaId}
                  size="sm"
                  variant="outline"
                  onClick={() => send("raise_hand_ack", { persona_id: p.personaId })}
                >
                  <Hand className="mr-1.5 h-3.5 w-3.5" />
                  Call on {p.displayName}
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* Control bar */}
        <div className="flex items-center justify-center gap-2 rounded-lg border bg-card p-3">
          {!joined ? (
            <Button onClick={join}>Join session</Button>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={toggleScreenShare}>
                <MonitorUp className="mr-1.5 h-4 w-4" />
                {screenSharing ? "Stop sharing" : "Share screen"}
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
      <aside className="flex w-80 shrink-0 flex-col rounded-lg border bg-card">
        <div className="border-b px-4 py-3">
          <h2 className="text-sm font-semibold">Transcript</h2>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4 text-sm">
          {transcript.length === 0 && (
            <p className="text-xs text-muted-foreground">
              The conversation will appear here.
            </p>
          )}
          {transcript.map((line, i) => (
            <div key={i}>
              <p className="text-xs font-medium text-muted-foreground">{line.speaker}</p>
              <p>{line.text}</p>
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>
      </aside>
    </div>
  );
}
