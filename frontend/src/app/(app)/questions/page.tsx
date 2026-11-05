import type { Metadata } from "next";

import { QuestionBank } from "@/components/questions/question-bank";

export const metadata: Metadata = { title: "题库 · AlphaJob" };

export default function QuestionsPage() {
  return <QuestionBank />;
}
