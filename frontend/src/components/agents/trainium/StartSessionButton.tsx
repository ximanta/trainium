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
      const res = await api.post("/trainium/simulations", {
        persona_ids: personaIds,
        mode: "practice",
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
