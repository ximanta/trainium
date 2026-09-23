import { SessionBuilder } from "@/components/agents/trainium/SessionBuilder";

export default function TrainiumAdminPage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold">Set up a session</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Choose the teaching material and the learners in the room, then share the link
        with your trainer.
      </p>
      <div className="mt-8">
        <SessionBuilder />
      </div>
    </main>
  );
}
