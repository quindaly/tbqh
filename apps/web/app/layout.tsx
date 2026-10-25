import "@fontsource-variable/newsreader/wght.css";
import "@fontsource-variable/instrument-sans/wght.css";
import "./globals.css";
import type { Metadata } from "next";
import NavBar from "./NavBar";

export const metadata: Metadata = {
  title: "TBQH — Group Discussion Prompts",
  description: "Let’s get to know each other",
};

// Runs before the page paints so a saved Light or Dark choice never flashes
// the other theme first.
const THEME_SCRIPT = `try{var t=localStorage.getItem("tbqh-theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-paper text-ink font-sans">
        <NavBar />
        <main className="max-w-2xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
