const withPWA = require('next-pwa')({
  dest: 'public',
  disable: true, // ✅ Force disable to fix cache loop
  register: true,
  skipWaiting: true,
  customWorkerDir: 'worker',
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export', // ✅ Required for Capacitor
  images: {
    unoptimized: true, // ✅ Required for static export
  },
  reactStrictMode: true,
  transpilePackages: ['rc-slider'], // ✅ Native transpiler for Next.js 13+
  generateBuildId: async () => {
    return 'build-' + Date.now();
  },
  experimental: {
    appDir: true,
  },
};

module.exports = withPWA(nextConfig);
