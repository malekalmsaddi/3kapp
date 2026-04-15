import NavBar from '@/components/NavBar';
import AuthGuard from '@/components/AuthGuard';

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1 p-6 max-w-[1400px] w-full mx-auto">
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
