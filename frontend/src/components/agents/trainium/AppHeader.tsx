import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { TrainiumLogo } from "@/components/agents/trainium/TrainiumLogo";

type Crumb = { label: string; href?: string };

/** Header shared by every view. Crumbs show where you are and let you go back
 *  up; the last one is the current page and is not a link. */
export function AppHeader({
  crumbs = [],
  action,
}: {
  crumbs?: Crumb[];
  action?: React.ReactNode;
}) {
  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-3.5">
        <TrainiumLogo />

        {crumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm">
            {crumbs.map((c, i) => {
              const last = i === crumbs.length - 1;
              return (
                <span key={c.label} className="flex min-w-0 items-center gap-1">
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300" />
                  {c.href && !last ? (
                    <Link href={c.href} className="truncate text-slate-500 hover:text-slate-900">
                      {c.label}
                    </Link>
                  ) : (
                    <span className="truncate font-medium text-slate-900" aria-current="page">
                      {c.label}
                    </span>
                  )}
                </span>
              );
            })}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2">{action}</div>
      </div>
    </header>
  );
}
