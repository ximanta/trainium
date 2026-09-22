"use client";

import { useEffect, useState } from "react";

import { api } from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { StartSessionButton } from "@/components/agents/trainium/StartSessionButton";

type PersonaTemplate = {
  id: string;
  name: string;
  type: string;
  profile: string;
  voice_id: string;
};

export function PersonaList() {
  const [personas, setPersonas] = useState<PersonaTemplate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<PersonaTemplate[]>("/trainium/personas")
      .then((res) => setPersonas(res.data))
      .catch(() => setError("Could not load personas. Is the backend running?"));
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {personas.map((persona) => (
          <Card
            key={persona.id}
            onClick={() => toggle(persona.id)}
            className={`cursor-pointer transition-colors ${
              selected.has(persona.id) ? "border-primary" : ""
            }`}
          >
            <CardHeader>
              <CardTitle>{persona.name}</CardTitle>
              <CardDescription>{persona.type.replace("_", " ")}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{persona.profile}</p>
              <p className="mt-2 text-xs text-muted-foreground">Voice: {persona.voice_id}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="mt-6">
        <StartSessionButton personaIds={Array.from(selected)} />
      </div>
    </div>
  );
}
