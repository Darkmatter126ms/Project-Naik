import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Naik · Cloud Path",
  description:
    "Naik — an agentic wealth & insurance layer inside Monee. Cloud-path status console.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
