const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export', // ✅ Required for Capacitor
  outputFileTracingRoot: path.join(__dirname, ".."),
  images: {
    unoptimized: true, // ✅ Required for static export
  },
  reactStrictMode: true,
  transpilePackages: ['rc-slider'], // ✅ Native transpiler for Next.js 13+
  generateBuildId: async () => {
    // Keep the tracked static export deterministic across local and CI builds.
    return process.env.NEXT_BUILD_ID || 'static-export';
  },
};

module.exports = nextConfig;
