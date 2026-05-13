/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  watchOptions: {
    pollIntervalMs: Number(process.env.NEXT_WATCH_POLL_INTERVAL_MS || "300"),
  },
};

export default nextConfig;
