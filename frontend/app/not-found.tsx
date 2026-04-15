import Link from 'next/link';
import GlassPanel from '../components/GlassPanel';

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <GlassPanel>
        <h1 className="mb-2 text-xl font-semibold text-red-500">
          404 - Page Not Found
        </h1>
        <p className="mb-4">The requested page does not exist.</p>
        <Link href="/" className="text-red-500 underline">
          Go home
        </Link>
      </GlassPanel>
    </div>
  );
}
