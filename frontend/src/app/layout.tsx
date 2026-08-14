import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PawSpective — See the world closer to how your dog sees it",
  description:
    "Explore a research-grounded approximation of canine vision and turn the moment into a playful story.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}