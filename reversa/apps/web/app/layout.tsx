import type { Metadata, Viewport } from "next";
import "./globals.css";
import Nav from "../components/Nav";

export const metadata: Metadata = {
  title: "REVERSA — AI operations, with recovery built in",
  description: "Execute and verify multi-system workflows. When something fails, REVERSA safely reverses what it can and records what happened.",
};

export const viewport: Viewport = { themeColor: "#0b0c0e", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <Nav />
        <main id="main-content" className="container" tabIndex={-1}>{children}</main>
      </body>
    </html>
  );
}
