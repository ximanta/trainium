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
      {/* Wider than a reading column: the report is scanned against a video
          beside it, not read top to bottom like prose. */}
      <main className="mx-auto max-w-6xl px-6 py-8">
        <SessionReport simulationId={params.id} />
      </main>
    </div>
  );
}
