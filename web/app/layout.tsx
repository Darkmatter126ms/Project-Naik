import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Naik · Panduan Keuangan Cerdas",
  description:
    "Naik — lapisan agentik di dalam Monee. Diagnosis keuangan, reksa dana, dan proteksi penghasilan untuk pengguna Shopee Indonesia.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: the inline script below sets data-theme before
    // React hydrates, so the attribute may differ from the server render. This
    // suppresses the expected mismatch warning without hiding real bugs.
    <html lang="id" suppressHydrationWarning>
      <head>
        {/*
          Theme flash prevention: read localStorage synchronously before the
          first paint so the correct theme is applied immediately. Must be a
          blocking inline script — an async import arrives too late.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('naik_theme');if(t==='light')document.documentElement.dataset.theme='light';}catch(e){}})();`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
