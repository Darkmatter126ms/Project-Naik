import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Naik · Panduan Keuangan Cerdas",
  description:
    "Naik — lapisan agentik di dalam Monee. Diagnosis keuangan, reksa dana, dan proteksi penghasilan untuk pengguna Shopee Indonesia.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
