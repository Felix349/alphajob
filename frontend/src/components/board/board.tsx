"use client";

import {
  DndContext,
  type DragEndEvent,
  type DragOverEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { useUpdateApplication } from "@/hooks/use-applications";
import type { Application, Stage } from "@/lib/api/applications";
import { STAGES } from "@/lib/stages";
import { cn } from "@/lib/utils";

import { ApplicationCard } from "./application-card";

type Columns = Record<Stage, Application[]>;

// 与后端 POSITION_GAP 一致
const GAP = 1024;
const COLUMN_PREFIX = "column:";

function groupByStage(apps: Application[]): Columns {
  const cols = Object.fromEntries(STAGES.map((s) => [s.value, [] as Application[]])) as Columns;
  for (const a of apps) cols[a.stage].push(a);
  for (const s of STAGES) cols[s.value].sort((a, b) => a.position - b.position);
  return cols;
}

/** 卡片放在 prev 和 next 之间时的新位置：取中间值，这样不用重排整列。 */
function positionBetween(prev?: number, next?: number): number {
  if (prev === undefined && next === undefined) return 0;
  if (prev === undefined) return next! - GAP;
  if (next === undefined) return prev + GAP;
  return (prev + next) / 2;
}

export function Board({ applications }: { applications: Application[] }) {
  const dndId = useId(); // 固定 id，避免服务端渲染和客户端的 aria 属性不一致
  const update = useUpdateApplication();
  const serverColumns = useMemo(() => groupByStage(applications), [applications]);
  // 拖拽过程中使用本地副本实时预览；松手并保存后再回到服务器数据
  const [dragColumns, setDragColumns] = useState<Columns | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const columns = dragColumns ?? serverColumns;

  const sensors = useSensors(
    // 移动超过 6px 才算拖拽，否则当作点击（打开详情页）
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function findStage(id: string, cols: Columns): Stage | undefined {
    if (id.startsWith(COLUMN_PREFIX)) return id.slice(COLUMN_PREFIX.length) as Stage;
    return STAGES.find((s) => cols[s.value].some((a) => a.id === id))?.value;
  }

  function onDragStart({ active }: DragStartEvent) {
    setActiveId(String(active.id));
    setDragColumns(serverColumns);
  }

  // 拖到另一列上方时，立即把卡片移过去（实时预览）
  function onDragOver({ active, over }: DragOverEvent) {
    if (!over) return;
    // 在 updater 里基于最新状态计算：dragOver 触发很频繁，闭包里的状态可能已经过期
    setDragColumns((prev) => {
      if (!prev) return prev;
      const from = findStage(String(active.id), prev);
      const to = findStage(String(over.id), prev);
      if (!from || !to || from === to) return prev;
      const moving = prev[from].find((a) => a.id === active.id)!;
      const target = prev[to];
      const overIndex = target.findIndex((a) => a.id === over.id);
      const insertAt = overIndex >= 0 ? overIndex : target.length;
      return {
        ...prev,
        [from]: prev[from].filter((a) => a.id !== active.id),
        [to]: [...target.slice(0, insertAt), { ...moving, stage: to }, ...target.slice(insertAt)],
      };
    });
  }

  function onDragEnd({ active, over }: DragEndEvent) {
    setActiveId(null);
    const cols = dragColumns;
    if (!over || !cols) {
      setDragColumns(null);
      return;
    }
    const stage = findStage(String(active.id), cols)!;
    let list = cols[stage];
    const oldIndex = list.findIndex((a) => a.id === active.id);
    const overIndex = list.findIndex((a) => a.id === over.id);
    if (overIndex >= 0 && overIndex !== oldIndex) list = arrayMove(list, oldIndex, overIndex);

    const index = list.findIndex((a) => a.id === active.id);
    const position = positionBetween(list[index - 1]?.position, list[index + 1]?.position);
    const original = applications.find((a) => a.id === active.id)!;

    if (original.stage === stage && index === serverColumns[stage].indexOf(original)) {
      setDragColumns(null); // 没有实际移动
      return;
    }

    setDragColumns({ ...cols, [stage]: list });
    update.mutate(
      { id: original.id, data: { stage, position } },
      {
        onError: (err) => toast.error(`移动失败：${err.message}`),
        onSettled: () => setDragColumns(null),
      },
    );
  }

  const active = activeId ? applications.find((a) => a.id === activeId) : undefined;

  return (
    <DndContext
      id={dndId}
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      onDragCancel={() => {
        setActiveId(null);
        setDragColumns(null);
      }}
    >
      <div className="flex gap-3 overflow-x-auto pb-4">
        {STAGES.map((s) => (
          <Column
            key={s.value}
            stage={s.value}
            label={s.label}
            dot={s.dot}
            apps={columns[s.value]}
          />
        ))}
      </div>
      <DragOverlay>{active ? <ApplicationCard app={active} overlay /> : null}</DragOverlay>
    </DndContext>
  );
}

function Column({
  stage,
  label,
  dot,
  apps,
}: {
  stage: Stage;
  label: string;
  dot: string;
  apps: Application[];
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `${COLUMN_PREFIX}${stage}` });
  return (
    <section className="flex w-64 shrink-0 flex-col rounded-xl bg-muted/50">
      <header className="flex items-center gap-2 px-3 pt-3 pb-2 text-sm font-medium">
        <span className={cn("size-2 rounded-full", dot)} />
        {label}
        <span className="ml-auto text-xs font-normal text-muted-foreground">{apps.length}</span>
      </header>
      <SortableContext items={apps.map((a) => a.id)} strategy={verticalListSortingStrategy}>
        <div
          ref={setNodeRef}
          className={cn(
            "flex min-h-24 flex-1 flex-col gap-2 rounded-b-xl px-2 pb-2 transition-colors",
            isOver && "bg-muted",
          )}
        >
          {apps.map((a) => (
            <SortableCard key={a.id} app={a} />
          ))}
          {apps.length === 0 && (
            <div className="rounded-lg border border-dashed py-6 text-center text-xs text-muted-foreground">
              拖到这里
            </div>
          )}
        </div>
      </SortableContext>
    </section>
  );
}

function SortableCard({ app }: { app: Application }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: app.id,
  });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
    >
      <ApplicationCard app={app} dragging={isDragging} />
    </div>
  );
}
