import { notFound } from "next/navigation";

import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { SessionEntry } from "@/components/agents/trainium/SessionEntry";
import type {
  GreenRoomPersona,
  GreenRoomSlide,
} from "@/components/agents/trainium/GreenRoom";

type JoinInfo = {
  simulation_id: string;
  title: string;
  course_title: string;
  audience: string;
  trainer_name: string;
  duration_min: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
};

async function resolveToken(token: string): Promise<JoinInfo | null> {
  // Resolved server-side so the trainer lands on a filled-in green room rather
  // than watching a client-side lookup spinner.
  const base = process.env.NEXT_PUBLIC_API_URL;
  const res = await fetch(`${base}/trainium/join/${token}`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export default async function TrainiumJoinPage({
  params,
}: {
  params: { token: string };
}) {
  const info = await resolveToken(params.token);
  if (!info) notFound();

  return (
    <div className="min-h-screen bg-white">
      <AppHeader crumbs={[{ label: info.title || "Live session" }]} />
      <main className="px-6 py-6">
        <SessionEntry
          simulationId={info.simulation_id}
          title={info.title || "Live session"}
          courseTitle={info.course_title}
          audience={info.audience}
          trainerName={info.trainer_name}
          durationMin={info.duration_min}
          personas={info.personas ?? []}
          slides={info.slides ?? []}
        />
      </main>
    </div>
  );
}
