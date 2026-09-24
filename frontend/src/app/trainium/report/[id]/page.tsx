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
      {/* The report renders its own masthead, so the page is only a frame. */}
      <main className="mx-auto max-w-3xl px-6 py-8">
        <SessionReport simulationId={params.id} />
      </main>
    </div>
  );
}
