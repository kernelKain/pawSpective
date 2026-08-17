import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "PawSpective — A warmer view from dog height",
    template: "%s · PawSpective",
  },
  description:
    "Explore a canine-vision approximation, compare toy colors, and turn a reviewed clip into a fictional animated dog story.",
  applicationName: "PawSpective",
  keywords: ["canine vision", "dog camera", "animated pet story"],
  icons: { icon: "/icon.svg" },
  openGraph: {
    title: "PawSpective",
    description:
      "Research-grounded approximations meet fictional dog-height storytelling.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
