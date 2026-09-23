import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { SessionBuilder } from "@/components/agents/trainium/SessionBuilder";

export default function TrainiumAdminPage() {
  return (
    <div className="min-h-screen bg-white">
      <AppHeader crumbs={[{ label: "Admin", href: "/trainium/admin" }, { label: "New session" }]} />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Set up a session</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the teaching material and the learners in the room, then share the link
          with your trainer.
        </p>
        <div className="mt-8">
          <SessionBuilder />
        </div>
      </main>
    </div>
  );
}
