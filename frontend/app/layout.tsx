import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import SuppressMetaMask from '@/components/SuppressMetaMask';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Moeen AI',
  description: 'AI-powered WhatsApp assistant dashboard',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <SuppressMetaMask />
        {/* Aurora animated background */}
        <div className="aurora-bg" aria-hidden="true">
          <div className="aurora-blob aurora-blob-1" />
          <div className="aurora-blob aurora-blob-2" />
          <div className="aurora-blob aurora-blob-3" />
        </div>
        {children}
      </body>
    </html>
  );
}
