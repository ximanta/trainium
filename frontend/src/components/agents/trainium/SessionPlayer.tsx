"use client";

import { forwardRef } from "react";
import { Download, Maximize2 } from "lucide-react";

/** The session recording.
 *
 *  Exposed by ref so evidence timecodes elsewhere in the report can seek it:
 *  reading "you said this at 0:43" is useful, watching yourself say it is
 *  more so, and that is the whole reason the recording exists.
 */
export const SessionPlayer = forwardRef<HTMLVideoElement, { simulationId: string }>(
  function SessionPlayer({ simulationId }, ref) {
    const src = `${process.env.NEXT_PUBLIC_API_URL}/trainium/sessions/${simulationId}/recording`;

    function expand() {
      const el = (ref as React.RefObject<HTMLVideoElement>)?.current;
      void el?.requestFullscreen?.();
    }

    return (
      <figure className="m-0">
        <div className="relative">
          {/* 16:9, so the box is the right shape before metadata loads and
              the column does not jump when it does. */}
          <video
            ref={ref}
            src={src}
            controls
            preload="metadata"
            playsInline
            className="aspect-video w-full rounded-lg bg-slate-900 object-cover"
          />
          {/* Top corner, clear of the browser's own controls along the
              bottom edge. */}
          <button
            type="button"
            onClick={expand}
            aria-label="Expand video to full screen"
            className="absolute right-2 top-2 cursor-pointer rounded-md bg-black/60 p-1.5 text-white backdrop-blur transition-colors hover:bg-black/80"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <figcaption className="mt-2 flex items-start justify-between gap-3 text-xs leading-relaxed text-muted-foreground">
          <span>Click any timecode to jump to that moment.</span>
          {/* A plain link, not a fetch: the browser streams it straight to
              disk rather than buffering the whole recording in memory. */}
          <a
            href={`${src}?download=true`}
            download
            className="flex shrink-0 items-center gap-1 font-medium text-slate-600 underline-offset-2 transition-colors hover:text-indigo-700 hover:underline"
          >
            <Download className="h-3.5 w-3.5" />
            Save
          </a>
        </figcaption>
      </figure>
    );
  }
);
