import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Timetable Admin",
  description: "Institutional timetable generation and management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
