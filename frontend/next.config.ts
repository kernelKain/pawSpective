import type { NextConfig } from "next";

if (
  process.env.VERCEL === "1" &&
  !process.env.NEXT_PUBLIC_API_BASE_URL?.trim()
) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL must be set before deploying PawSpective to Vercel.",
  );
}

const nextConfig: NextConfig = {
  output: "standalone",

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=()",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
