const isDevServer = process.env.NODE_ENV === "development";

/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  // Keep the reused local dev server stable while `npm run build` writes the
  // production bundle in the same workspace.
  distDir: isDevServer ? ".next-dev" : ".next",
  watchOptions: {
    pollIntervalMs: Number(process.env.NEXT_WATCH_POLL_INTERVAL_MS || "300"),
  },
};

export default nextConfig;
