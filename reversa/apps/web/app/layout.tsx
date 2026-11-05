import type { Metadata } from "next";
import "./globals.css";
import Nav from "../components/Nav";

export const metadata: Metadata = {
  title: "REVERSA — Self-Healing AI Operations",
  description: "AI that doesn't just act. It makes things right.",
};

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
