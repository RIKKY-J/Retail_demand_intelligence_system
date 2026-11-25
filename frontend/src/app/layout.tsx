import type { Metadata } from "next";
import "./globals.css";
import { SidebarLayout } from "@/components/ui/SidebarLayout";

export const metadata: Metadata = {
  title: "RetailPulse AI | Retail Inventory & Demand Intelligence",
  description:
    "AI-powered retail demand forecasting (LightGBM Tweedie) and forecast-aware inventory replenishment dashboard.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <SidebarLayout>{children}</SidebarLayout>
      </body>
    </html>
  );
}
