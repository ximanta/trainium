"use client";

import { useEffect, useRef, useState } from "react";
import { MicVAD } from "@ricky0123/vad-web";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type PersonaTileState = {
  personaId: string;
  speaking: boolean;
  lastLine: string | null;
};

type TranscriptLine = {
  speaker: string;
  text: string;
  ts: number;
};

const CHUNK_FRAMES = 1600; // ~100ms at 16kHz, matches Gemini's expected chunk size

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

export function TrainiumClassroom({ simulationId }: { simulationId: string }) {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [personas, setPersonas] = useState<Record<string, PersonaTileState>>({});

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const playbackQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);

  useEffect(() => {
    return () => {
      vadRef.current?.destroy();
      wsRef.current?.close();
      audioContextRef.current?.close();
    };
  }, []);

  async function playChunk(bytes: ArrayBuffer, ctx: AudioContext): Promise<void> {
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

  async function startSession() {
    setStatus("requesting mic access...");
    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000 },
    });
    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, "ws")}/trainium/ws/session`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ simulation_id: simulationId }));
    };

    ws.onmessage = async (event) => {
      if (typeof event.data !== "string") return;
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case "ready":
          setStatus("listening");
          await startVAD(ws, micStream, audioContext);
          break;
        case "final_transcript":
          setTranscript((prev) => [
            ...prev,
            { speaker: "trainer", text: msg.data.text, ts: msg.data.ts },
          ]);
          break;
        case "persona_speaking":
          setPersonas((prev) => ({
            ...prev,
            [msg.data.persona_id]: {
              personaId: msg.data.persona_id,
              speaking: true,
              lastLine: msg.data.text,
            },
          }));
          setTranscript((prev) => [
            ...prev,
            { speaker: msg.data.persona_id, text: msg.data.text, ts: 0 },
          ]);
          break;
        case "persona_audio": {
          const audioBuffer = base64ToArrayBuffer(msg.data.b64);
          playbackQueueRef.current.push(audioBuffer);
          drainPlaybackQueue(audioContext);
          break;
        }
        case "persona_done":
          setPersonas((prev) => {
            const next = { ...prev };
            for (const key of Object.keys(next)) {
              if (next[key].speaking) next[key] = { ...next[key], speaking: false };
            }
            return next;
          });
          break;
        case "error":
          setStatus(`error: ${msg.data.message}`);
          break;
      }
    };

    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("connection error");
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
        setStatus("speaking...");
        ws.send(JSON.stringify({ type: "activity_start" }));
      },
      onSpeechEnd: () => {
        speaking = false;
        setStatus("processing...");
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

  function bargeIn() {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "barge_in" }));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <div>
        <div className="flex items-center gap-3">
          <Button onClick={startSession} disabled={status !== "idle"}>
            Start session
          </Button>
          <Button variant="outline" onClick={bargeIn} disabled={status === "idle"}>
            Barge in
          </Button>
          <span className="text-sm text-muted-foreground">{status}</span>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Object.values(personas).map((p) => (
            <Card key={p.personaId} className={p.speaking ? "border-primary" : undefined}>
              <CardHeader>
                <CardTitle className="text-sm">{p.personaId}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {p.speaking ? "Speaking..." : "Listening"}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium text-muted-foreground">Transcript</h2>
        <div className="mt-2 h-96 overflow-y-auto rounded-md border p-3 text-sm">
          {transcript.map((line, i) => (
            <p key={i} className="mb-2">
              <span className="font-medium">{line.speaker}: </span>
              {line.text}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
