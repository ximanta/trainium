import Link from "next/link";

/** The wordmark, used in every view's header so the product reads as one app. */
export function TrainiumLogo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="text-lg font-bold tracking-tight text-slate-900">
      trainium<span className="text-emerald-500">.</span>
    </Link>
  );
}
