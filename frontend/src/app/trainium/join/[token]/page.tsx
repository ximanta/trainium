import { notFound } from "next/navigation";

import { TrainiumClassroom } from "@/components/agents/trainium/TrainiumClassroom";

type JoinInfo = {
  simulation_id: string;
  title: string;
};

async function resolveToken(token: string): Promise<JoinInfo | null> {
  // Resolved server-side so the trainer lands straight in the classroom
  // rather than watching a client-side lookup spinner.
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
    <main className="px-6 py-6">
      <h1 className="text-xl font-semibold">{info.title || "Live session"}</h1>
      <p className="mt-0.5 text-xs text-muted-foreground">
        You are joining as the trainer.
      </p>
      <div className="mt-4">
        <TrainiumClassroom simulationId={info.simulation_id} />
      </div>
    </main>
  );
}
