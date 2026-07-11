import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Consent-Based Voice Cloning Demo",
  description: "Cybersecurity education proof-of-concept -- local, consent-based voice cloning demo.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="nav">
          <Link href="/" className="nav-title">
            Voice Clone Consent Demo
          </Link>
          <Link href="/">Create Session</Link>
          <Link href="/safety">Safety &amp; Risks</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
