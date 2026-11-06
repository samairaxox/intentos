import type { Metadata } from "next";
import "./globals.css";
import LocalAccess from "@/components/LocalAccess";
export const metadata: Metadata = {
  title: "IntentOS | Purchase workspace",
  description:
    "Approval-controlled AI purchasing with demo products and simulated payments",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body><LocalAccess />{children}</body>
    </html>
  );
}
