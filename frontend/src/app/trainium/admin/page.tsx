import Link from "next/link";
import { Plus } from "lucide-react";

import { AppHeader } from "@/components/agents/trainium/AppHeader";
import { SessionList } from "@/components/agents/trainium/SessionList";
import { Button } from "@/components/ui/button";

export default function TrainiumAdminPage() {
  return (
    <div className="min-h-screen bg-white">
      <AppHeader crumbs={[{ label: "Admin" }]} />
      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Sessions</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Every session you have set up. Copy a link to share it again, or edit
              the material and learners before it runs.
            </p>
          </div>
          <Button asChild className="shrink-0">
            <Link href="/trainium/admin/new">
              <Plus className="mr-1.5 h-4 w-4" />
              New session
            </Link>
          </Button>
        </div>
        <div className="mt-6">
          <SessionList />
        </div>
      </main>
    </div>
  );
}
