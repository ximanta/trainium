"use client";

import { useEffect, useState } from "react";

import { api } from "@/api/axios";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

type PersonaTemplate = {
  id: string;
  name: string;
  type: string;
  profile: string;
  voice_id: string;
};

export function PersonaList() {
  const [personas, setPersonas] = useState<PersonaTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<PersonaTemplate[]>("/trainium/personas")
      .then((res) => setPersonas(res.data))
      .catch(() => setError("Could not load personas. Is the backend running?"));
  }, []);

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {personas.map((persona) => (
        <Card key={persona.id}>
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
  );
}
