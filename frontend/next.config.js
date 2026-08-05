/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Emit .next/standalone -- a self-contained server plus only the node_modules
  // actually reached by the build. The Docker image copies that instead of the
  // full dependency tree.
  output: 'standalone',

  eslint: {
    // Lint is a separate CI/dev step (`npm run lint`); a Docker build should
    // not fail on a style rule.
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;
