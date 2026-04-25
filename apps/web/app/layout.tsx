import "./globals.css";
import type { Metadata } from "next";
import NavBar from "./NavBar";

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
        <NavBar />
        <main className="max-w-2xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
