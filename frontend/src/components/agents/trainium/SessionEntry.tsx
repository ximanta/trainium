"use client";

import { useState } from "react";

import {
  GreenRoom,
  type GreenRoomPersona,
  type GreenRoomSlide,
  type TrainerAddress,
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
  trainerEmail,
  durationMin,
  personas,
  slides,
}: {
  simulationId: string;
  title: string;
  courseTitle: string;
  audience: string;
  trainerName: string;
  trainerEmail: string;
  durationMin: number;
  personas: GreenRoomPersona[];
  slides: GreenRoomSlide[];
}) {
  // Whoever opened the link, as they identified themselves in the green room.
  const [identity, setIdentity] = useState<{
    name: string;
    email: string;
    address: TrainerAddress;
  } | null>(null);

  if (!identity) {
    return (
      <GreenRoom
        title={title}
        courseTitle={courseTitle}
        audience={audience}
        trainerName={trainerName}
        trainerEmail={trainerEmail}
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
      trainerName={identity.name}
      trainerEmail={identity.email}
      trainerAddress={identity.address}
    />
  );
}
