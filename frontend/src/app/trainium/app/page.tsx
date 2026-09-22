import { PersonaList } from "@/components/agents/trainium/PersonaList";

export default function TrainiumAppPage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <h1 className="text-2xl font-semibold">Your sessions</h1>
      <p className="mt-2 text-muted-foreground">
        Log in, join a session, and view your report here. This route is reserved for
        the trainer role.
      </p>
      <h2 className="mt-10 text-lg font-medium">Available personas</h2>
      <div className="mt-4">
        <PersonaList />
      </div>
    </main>
  );
}
