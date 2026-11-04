import { CalendarClock, MapPin } from "lucide-react";
import Link from "next/link";

import type { Application } from "@/lib/api/applications";
import { formatDateTime, relativeDay } from "@/lib/format";
import { EVENT_TYPE_LABEL } from "@/lib/stages";
import { cn } from "@/lib/utils";

export function ApplicationCard({
  app,
  dragging = false,
  overlay = false,
}: {
  app: Application;
  dragging?: boolean;
  overlay?: boolean;
}) {
  const next = app.next_event;
  return (
    <Link
      href={`/applications/${app.id}`}
      draggable={false}
      className={cn(
        "block rounded-lg border bg-card p-3 text-left shadow-xs transition-shadow hover:shadow-sm",
        dragging && "opacity-40",
        overlay && "rotate-1 shadow-lg",
      )}
    >
      <div className="truncate font-medium">{app.company}</div>
      <div className="mt-0.5 truncate text-sm text-muted-foreground">{app.role}</div>
      {app.location && (
        <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin className="size-3" />
          <span className="truncate">{app.location}</span>
        </div>
      )}
      {next && (
        <div className="mt-2 flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <CalendarClock className="size-3 shrink-0" />
          <span className="truncate">
            {relativeDay(next.start_at)} · {EVENT_TYPE_LABEL[next.type]}「{next.title}」
          </span>
          <span className="sr-only">{formatDateTime(next.start_at)}</span>
        </div>
      )}
    </Link>
  );
}
