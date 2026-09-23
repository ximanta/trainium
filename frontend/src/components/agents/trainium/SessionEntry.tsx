"use client";

import { useState } from "react";

import {
  GreenRoom,
  type GreenRoomPersona,
  type GreenRoomSlide,
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
  trainerName,
  durationMin,
  personas,
  slides,
}: {
  simulationId: string;
  title: string;
  courseTitle: string;
  audience: string;
  trainerName: string;
  durationMin: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
}) {
  const [started, setStarted] = useState(false);

  if (!started) {
    return (
      <GreenRoom
        title={title}
        courseTitle={courseTitle}
        audience={audience}
        trainerName={trainerName}
        durationMin={durationMin}
        personas={personas}
        slides={slides}
        onStart={() => setStarted(true)}
      />
    );
  }

  return <TrainiumClassroom simulationId={simulationId} autoJoin />;
}
