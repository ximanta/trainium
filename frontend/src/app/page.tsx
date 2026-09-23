import Link from "next/link";

const PIPELINE = [
  {
    tag: "ingest",
    title: "Slides become a teaching graph",
    body: "Your material becomes the beats the Director expects the session to hit.",
  },
  {
    tag: "direct",
    title: "Turn-controlled session",
    body: "Personas never self-initiate speech. The Director gates every turn.",
  },
  {
    tag: "record",
    title: "Full-fidelity capture",
    body: "Audio, video and transcript are captured together, timestamp-aligned.",
  },
  {
    tag: "analyse",
    title: "Evidence-backed report",
    body: "An analysis pipeline scores the session and cites its source.",
  },
];

const PERSONAS = [
  { name: "Priya", type: "Curious", body: "Asks questions that connect to what you already covered." },
  { name: "Devon", type: "Skeptic", body: "Pushes back until the reasoning actually holds." },
  { name: "Amara", type: "Confused", body: "Misunderstands, and needs it put a different way." },
  { name: "Tomas", type: "Silent", body: "Says nothing unless you notice and draw him in." },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-lg font-bold tracking-tight">
            trainium<span className="text-emerald-500">.</span>
          </span>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="#pipeline" className="hidden text-slate-600 hover:text-slate-900 sm:block">
              Pipeline
            </Link>
            <Link href="#personas" className="hidden text-slate-600 hover:text-slate-900 sm:block">
              Personas
            </Link>
            <Link
              href="/trainium/admin"
              className="rounded-md bg-slate-900 px-3.5 py-2 font-medium text-white hover:bg-slate-700"
            >
              Admin
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <p className="font-mono text-xs tracking-wide text-indigo-700">
            &gt; simulated classroom, real signal
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            A live classroom of AI personas to pressure test how you teach.
          </h1>
          <p className="mt-5 max-w-2xl text-slate-600">
            Trainium runs your session against a director-controlled cast of learner
            personas, streams the turn-by-turn interaction, and hands the recording to
            Gemini to produce a coaching report where every score traces back to a moment
            in the transcript.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/trainium/admin"
              className="rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Set up a session
            </Link>
            <Link
              href="#pipeline"
              className="rounded-md border px-5 py-2.5 text-sm font-medium hover:bg-slate-50"
            >
              See how it works
            </Link>
          </div>

          <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-3 text-sm text-slate-500">
            <div>
              <dt className="inline font-mono text-slate-900">4+</dt>{" "}
              <dd className="inline">personas per session</dd>
            </div>
            <div>
              <dt className="inline font-mono text-slate-900">live</dt>{" "}
              <dd className="inline">slide-aware questions</dd>
            </div>
            <div>
              <dt className="inline font-mono text-slate-900">100%</dt>{" "}
              <dd className="inline">evidence-cited scores</dd>
            </div>
          </dl>
        </section>

        <section id="pipeline" className="border-t bg-slate-50">
          <div className="mx-auto max-w-6xl px-6 py-14">
            <p className="font-mono text-xs tracking-wide text-indigo-700">&gt; the pipeline</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">
              Upload, teach, and let the graph do the rest.
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Ingestion, live session and analysis are three separate stages, each
              independently inspectable.
            </p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {PIPELINE.map((step) => (
                <div key={step.tag} className="rounded-lg border bg-white p-5">
                  <span className="rounded bg-emerald-50 px-2 py-0.5 font-mono text-xs text-emerald-700">
                    {step.tag}
                  </span>
                  <h3 className="mt-3 font-medium">{step.title}</h3>
                  <p className="mt-2 text-sm text-slate-600">{step.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="personas" className="border-t">
          <div className="mx-auto max-w-6xl px-6 py-14">
            <p className="font-mono text-xs tracking-wide text-indigo-700">&gt; the cast</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">
              Learners tuned to expose specific gaps.
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Each persona reacts to what you actually say, not a fixed script. Admins
              rename them, retune how often they speak, and set who the cohort is.
            </p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {PERSONAS.map((p) => (
                <div key={p.name} className="rounded-lg border p-5">
                  <p className="font-medium">{p.name}</p>
                  <p className="font-mono text-xs text-slate-500">{p.type}</p>
                  <p className="mt-2 text-sm text-slate-600">{p.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t bg-slate-50">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-6 px-6 py-12">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">
                Run your first simulated session.
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Set it up as an admin, then send your trainer the join link.
              </p>
            </div>
            <Link
              href="/trainium/admin"
              className="rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Set up a session
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto max-w-6xl px-6 py-6 font-mono text-xs text-slate-500">
          trainium, ai trainer simulator
        </div>
      </footer>
    </div>
  );
}
