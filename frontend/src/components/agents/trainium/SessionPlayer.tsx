"use client";

import { forwardRef } from "react";
import { Video } from "lucide-react";

/** The session recording, as a normal video element.
 *
 *  Exposed by ref so evidence timecodes elsewhere in the report can seek it:
 *  reading "you said this at 0:43" is useful, watching yourself say it is
 *  more so, and that is the whole reason the recording exists.
 */
export const SessionPlayer = forwardRef<HTMLVideoElement, { simulationId: string }>(
  function SessionPlayer({ simulationId }, ref) {
    const src = `${process.env.NEXT_PUBLIC_API_URL}/trainium/sessions/${simulationId}/recording`;
    return (
      <figure className="m-0">
        <video
          ref={ref}
          src={src}
          controls
          preload="metadata"
          className="w-full rounded-xl bg-slate-900"
          // Without this the first frame is black until the user presses play,
          // which reads as a broken player rather than a paused one.
          playsInline
        />
        <figcaption className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Video className="h-3.5 w-3.5" />
          Your camera track. Click any timecode below to jump to that moment.
        </figcaption>
      </figure>
    );
  }
);
