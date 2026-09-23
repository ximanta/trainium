import { TrainiumClassroom } from "@/components/agents/trainium/TrainiumClassroom";

export default function TrainiumSessionPage({ params }: { params: { id: string } }) {
  return (
    <main className="px-6 py-6">
      <h1 className="text-xl font-semibold">Live session</h1>
      <p className="mt-0.5 text-xs text-muted-foreground">Session {params.id}</p>
      <div className="mt-4">
        <TrainiumClassroom simulationId={params.id} />
      </div>
    </main>
  );
}
