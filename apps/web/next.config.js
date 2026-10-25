/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async redirects() {
    return [
      // The Hot Seat's old address. Shared invite links (?code=...) keep working.
      {
        source: "/games/how-well-do-you-know",
        destination: "/games/the-hot-seat",
        permanent: true,
      },
    ];
  },
};

module.exports = nextConfig;
