"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";

/** What happens between pressing start and the room being live.
 *
 *  Named steps rather than a spinner: connecting takes a few seconds and the
 *  trainer is about to teach, so telling them the learners are taking their
 *  seats is calmer than an anonymous wait. The steps are real stages of the
 *  join, though they advance on a timer rather than on each backend event,
 *  since some stages report nothing until they finish.
 */
const STEPS = [
  "Opening the room",
  "Learners taking their seats",
  "Putting your material on screen",
  "Listening for you",
];

export function ClassroomLoading({ personaNames }: { personaNames: string[] }) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    // Stops one short of the end: the last step completes when the session
    // actually opens, so the list never claims to be finished while the
    // trainer is still waiting.
    const timer = setInterval(
      () => setStep((s) => Math.min(s + 1, STEPS.length - 1)),
      900
    );
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3">
          {/* Three dots settling into place, echoing the persona tiles that
              are about to appear. */}
          <span className="flex gap-1.5" aria-hidden="true">
            {[0, 200, 400].map((delay) => (
              <span
                key={delay}
                style={{ animationDelay: `${delay}ms` }}
                className="h-2 w-2 animate-bounce rounded-full bg-indigo-500"
              />
            ))}
          </span>
          <p className="text-sm font-medium">Starting your session</p>
        </div>

        <ol className="mt-6 flex flex-col gap-3">
          {STEPS.map((label, i) => {
            const done = i < step;
            const active = i === step;
            return (
              <li
                key={label}
                className={`flex items-center gap-2.5 text-sm transition-colors ${
                  done
                    ? "text-muted-foreground"
                    : active
                      ? "font-medium text-slate-900"
                      : "text-slate-300"
                }`}
              >
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                    done
                      ? "border-green-600 bg-green-600"
                      : active
                        ? "border-indigo-500"
                        : "border-slate-200"
                  }`}
                >
                  {done && <Check className="h-2.5 w-2.5 text-white" />}
                  {active && <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />}
                </span>
                {label}
              </li>
            );
          })}
        </ol>

        {personaNames.length > 0 && (
          <p className="mt-6 border-t pt-4 text-xs leading-relaxed text-muted-foreground">
            {personaNames.slice(0, 4).join(", ")}
            {personaNames.length > 4 && ` and ${personaNames.length - 4} more`} will be
            in the room with you.
          </p>
        )}
      </div>
    </div>
  );
}
