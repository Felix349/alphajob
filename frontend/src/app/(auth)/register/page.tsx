import type { Metadata } from "next";

import { AuthForm } from "@/components/auth/auth-form";

export const metadata: Metadata = { title: "注册 · AlphaJob" };

export default function RegisterPage() {
  return <AuthForm mode="register" />;
}
