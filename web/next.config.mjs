/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep CI/sandbox builds deterministic: type errors still fail the build
  // (we want that), but ESLint is optional and not configured in this scaffold.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
