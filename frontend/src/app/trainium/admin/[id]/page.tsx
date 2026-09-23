import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { SessionBuilder } from "@/components/agents/trainium/SessionBuilder";

export default function TrainiumEditSessionPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <div className="min-h-screen bg-white">
      <AppHeader
        crumbs={[{ label: "Admin", href: "/trainium/admin" }, { label: "Edit session" }]}
      />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Edit session</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Changes apply to the same join link, so a trainer you already sent it to gets
          the updated session.
        </p>
        <div className="mt-8">
          <SessionBuilder sessionId={params.id} />
        </div>
      </main>
    </div>
  );
}
