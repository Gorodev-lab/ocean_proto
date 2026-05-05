import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZOHAR // Ocean Proto — Megafauna-Vessel Collision Risk Analyzer",
  description:
    "Geospatial analysis platform for cetacean-vessel collision risk assessment in the Gulf of California, powered by Global Fishing Watch and OBIS data.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
