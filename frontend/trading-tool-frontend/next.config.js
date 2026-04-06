const path = require('path');
const withTM = require('next-transpile-modules')(['rc-slider']); // ✅ Transpile rc-slider

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  experimental: {
    appDir: true,
  },

  webpack: (config, { isServer }) => {
    // ✅ CSS verwerken (ook uit node_modules)
    config.module.rules.push({
      test: /\.css$/i,
      use: ['style-loader', 'css-loader', 'postcss-loader'],
    });

    // ✅ Pad-aliases
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.resolve(__dirname),
      '@components': path.resolve(__dirname, 'components'),
      '@app': path.resolve(__dirname, 'app'),
      '@hooks': path.resolve(__dirname, 'hooks'),
      '@lib': path.resolve(__dirname, 'lib'),
      '@styles': path.resolve(__dirname, 'styles'),
      '@ui': path.resolve(__dirname, 'components/ui'),
    };

    // ✅ Fallbacks voor client-side imports
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        path: false,
      };
    }

    return config;
  },
};

module.exports = withTM(nextConfig); // ✅ gebruik wrapper
