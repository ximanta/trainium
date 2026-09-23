import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { SessionReport } from "@/components/agents/trainium/SessionReport";

export default function TrainiumReportPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <div className="min-h-screen bg-white">
      <AppHeader crumbs={[{ label: "Session report" }]} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Session report</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every score below cites the moment in your session it came from.
        </p>
        <div className="mt-8">
          <SessionReport simulationId={params.id} />
        </div>
      </main>
    </div>
  );
}
