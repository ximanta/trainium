import { TrainiumClassroom } from "@/components/agents/trainium/TrainiumClassroom";

export default function TrainiumSessionPage({ params }: { params: { id: string } }) {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold">Live session</h1>
      <p className="mt-1 text-sm text-muted-foreground">Session {params.id}</p>
      <div className="mt-6">
        <TrainiumClassroom simulationId={params.id} />
      </div>
    </main>
  );
}
