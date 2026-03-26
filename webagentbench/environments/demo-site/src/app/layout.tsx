import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WebAgentBench",
  description: "A benchmark for evaluating web agents on cognitive primitives",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
