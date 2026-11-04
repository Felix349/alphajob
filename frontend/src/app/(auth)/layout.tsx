export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center bg-muted/40 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">AlphaJob</h1>
          <p className="mt-1 text-sm text-muted-foreground">掌握你全部求职数据的求职 Agent</p>
        </div>
        {children}
      </div>
    </main>
  );
}
