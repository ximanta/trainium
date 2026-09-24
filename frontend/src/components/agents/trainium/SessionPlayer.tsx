"use client";

import { forwardRef } from "react";
import { Maximize2 } from "lucide-react";

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
          <video
            ref={ref}
            src={src}
            controls
            preload="metadata"
            playsInline
            className="w-full rounded-lg bg-slate-900"
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
        <figcaption className="mt-2 text-xs leading-relaxed text-muted-foreground">
          Click any timecode to jump to that moment.
        </figcaption>
      </figure>
    );
  }
);
