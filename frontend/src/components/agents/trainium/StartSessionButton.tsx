"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/api/axios";
import { Button } from "@/components/ui/button";

export function StartSessionButton({ personaIds }: { personaIds: string[] }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    try {
      // Practice sessions started from this screen use short cooldowns so the
      // classroom stays conversational. The realistic defaults (45s between
      // interventions, 180s per persona) are tuned for a full 30-minute class
      // and make a short practice run look unresponsive.
      const res = await api.post("/trainium/simulations", {
        persona_ids: personaIds,
        mode: "practice",
        min_gap_s: 10,
        per_persona_cooldown_s: 25,
      });
      router.push(`/trainium/app/session/${res.data.id}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button onClick={handleClick} disabled={loading || personaIds.length === 0}>
      {loading ? "Starting..." : "Start session with selected personas"}
    </Button>
  );
}
