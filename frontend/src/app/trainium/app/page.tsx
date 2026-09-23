import Link from "next/link";

export default function TrainiumAppPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-20 text-center">
      <h1 className="text-2xl font-semibold">Join a session from your link</h1>
      <p className="mt-3 text-sm text-muted-foreground">
        Sessions are set up by an admin, who picks the teaching material and the
        learners in the room. Open the link they sent you and you will land straight in
        the classroom, with everything already configured.
      </p>
      <p className="mt-6 text-sm text-muted-foreground">
        Setting sessions up yourself?{" "}
        <Link href="/trainium/admin" className="font-medium underline">
          Go to the admin console
        </Link>
        .
      </p>
    </main>
  );
}
