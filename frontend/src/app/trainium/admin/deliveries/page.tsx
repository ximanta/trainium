import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { RunList } from "@/components/agents/trainium/RunList";

export default function TrainiumDeliveriesPage({
  searchParams,
}: {
  // Set when arriving from a session row, so the list opens narrowed to that
  // configured session rather than every delivery ever.
  searchParams: { session?: string };
}) {
  return (
    <div className="min-h-screen bg-white">
      <AppHeader
        crumbs={[{ label: "Admin", href: "/trainium/admin" }, { label: "Deliveries" }]}
      />
      <main className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Deliveries</h1>
        <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">
          Every time a trainer has taught one of your sessions. A join link can be
          shared, so one configured session may appear here several times, once per
          trainer, each with its own transcript and report.
        </p>
        <div className="mt-6">
          <RunList simulationId={searchParams.session} />
        </div>
      </main>
    </div>
  );
}
