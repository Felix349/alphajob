"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CURRENT_USER_KEY } from "@/hooks/use-current-user";
import { authApi } from "@/lib/api/auth";

// 前端校验规则与后端 Pydantic 保持一致（密码 8–128 位）
const loginSchema = z.object({
  email: z.email({ error: "请输入有效的邮箱地址" }),
  password: z.string().min(1, { error: "请输入密码" }),
});

const registerSchema = z.object({
  display_name: z.string().max(64, { error: "昵称最多 64 个字符" }).optional(),
  email: z.email({ error: "请输入有效的邮箱地址" }),
  password: z.string().min(8, { error: "密码至少 8 位" }).max(128, { error: "密码最多 128 位" }),
});

type Mode = "login" | "register";
type FormValues = z.infer<typeof registerSchema>;

const COPY = {
  login: {
    title: "登录",
    description: "欢迎回来，继续你的求职计划",
    submit: "登录",
    switchText: "还没有账号？",
    switchLink: "注册",
    switchHref: "/register",
  },
  register: {
    title: "创建账号",
    description: "用一个账号管理你全部的求职数据",
    submit: "注册并登录",
    switchText: "已经有账号？",
    switchLink: "登录",
    switchHref: "/login",
  },
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const copy = COPY[mode];

  const form = useForm<FormValues>({
    resolver: zodResolver(mode === "login" ? loginSchema : registerSchema) as never,
    defaultValues: { email: "", password: "", display_name: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      mode === "login"
        ? authApi.login({ email: values.email, password: values.password })
        : authApi.register({
            email: values.email,
            password: values.password,
            display_name: values.display_name || null,
          }),
    onSuccess: (user) => {
      queryClient.setQueryData(CURRENT_USER_KEY, user);
      toast.success(mode === "login" ? "登录成功" : "注册成功");
      router.replace("/board");
      router.refresh();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const { errors } = form.formState;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{copy.title}</CardTitle>
        <CardDescription>{copy.description}</CardDescription>
      </CardHeader>
      <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))} noValidate>
        <CardContent className="flex flex-col gap-4">
          {mode === "register" && (
            <Field label="昵称（可选）" id="display_name" error={errors.display_name?.message}>
              <Input id="display_name" autoComplete="nickname" {...form.register("display_name")} />
            </Field>
          )}
          <Field label="邮箱" id="email" error={errors.email?.message}>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              aria-invalid={!!errors.email}
              {...form.register("email")}
            />
          </Field>
          <Field label="密码" id="password" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              aria-invalid={!!errors.password}
              {...form.register("password")}
            />
          </Field>
        </CardContent>
        <CardFooter className="mt-2 flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "请稍候…" : copy.submit}
          </Button>
          <p className="text-sm text-muted-foreground">
            {copy.switchText}
            <Link href={copy.switchHref} className="ml-1 font-medium text-foreground underline">
              {copy.switchLink}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}

function Field({
  label,
  id,
  error,
  children,
}: {
  label: string;
  id: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
