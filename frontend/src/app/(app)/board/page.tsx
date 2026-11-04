import type { Metadata } from "next";

import { BoardView } from "@/components/board/board-view";

export const metadata: Metadata = { title: "求职看板 · AlphaJob" };

export default function BoardPage() {
  return <BoardView />;
}
