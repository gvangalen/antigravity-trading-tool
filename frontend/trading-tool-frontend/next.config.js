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
};

module.exports = nextConfig;
