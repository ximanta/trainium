"use client";

import { useState } from "react";

import {
  GreenRoom,
  type GreenRoomPersona,
  type GreenRoomSlide,
  type TrainerIdentity,
} from "@/components/agents/trainium/GreenRoom";
import { TrainiumClassroom } from "@/components/agents/trainium/TrainiumClassroom";

/** Green room until the trainer starts, then the classroom.
 *
 *  A switch rather than two routes: the green room releases the camera and mic
 *  on start and the classroom immediately reopens them, which only works
 *  cleanly if no navigation happens in between.
 */
export function SessionEntry({
  simulationId,
  title,
  courseTitle,
  audience,
  requiresCode,
  durationMin,
  personas,
  slides,
}: {
  simulationId: string;
  title: string;
  courseTitle: string;
  audience: string;
  requiresCode: boolean;
  durationMin: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
}) {
  // Whoever opened the link, as they identified themselves in the green room.
  const [identity, setIdentity] = useState<TrainerIdentity | null>(null);

  if (!identity) {
    return (
      <GreenRoom
        title={title}
        courseTitle={courseTitle}
        audience={audience}
        requiresCode={requiresCode}
        durationMin={durationMin}
        personas={personas}
        slides={slides}
        onStart={setIdentity}
      />
    );
  }

  return (
    <TrainiumClassroom
      simulationId={simulationId}
      autoJoin
      code={identity.code}
      displayName={identity.displayName}
      trainerAddress={identity.address}
    />
  );
}
