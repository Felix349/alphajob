import { redirect } from "next/navigation";

// 首页直接进入看板；未登录时 proxy.ts 会先把用户带到登录页
export default function Home() {
  redirect("/board");
}
