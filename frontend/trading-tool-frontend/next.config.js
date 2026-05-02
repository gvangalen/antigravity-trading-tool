const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  skipWaiting: true,
  customWorkerDir: 'worker',
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export', // ✅ Required for Capacitor
  trailingSlash: true, // ✅ Required for pretty URLs in static export
  images: {
    unoptimized: true, // ✅ Required for static export
  },
  reactStrictMode: true,
  transpilePackages: ['rc-slider'], // ✅ Native transpiler for Next.js 13+
  experimental: {
    appDir: true,
  },
};

module.exports = withPWA(nextConfig);
