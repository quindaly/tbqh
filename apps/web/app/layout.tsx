import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "TBQH — Group Discussion Prompts",
  description: "Personalized discussion questions for your group",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
        <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-3 flex items-center justify-between">
          <a href="/" className="text-xl font-bold tracking-tight">
            tbqh
          </a>
          <div className="flex gap-4 text-sm">
            <a href="/dashboard" className="hover:underline">
              Dashboard
            </a>
            <a href="/favorites" className="hover:underline">
              Favorites
            </a>
            <a href="/blocked" className="hover:underline">
              Blocked
            </a>
          </div>
        </nav>
        <main className="max-w-2xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
