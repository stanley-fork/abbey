/** @type {import('next').NextConfig} */
module.exports = {
    transpilePackages: ['@mdxeditor/editor', 'react-diff-view'],
    reactStrictMode: false,
    images: {
        // domains: ['abbey-collections-images.s3.amazonaws.com', 'art-history-images.s3.amazonaws.com', ...(process.env.IMAGE_DOMAINS ? process.env.IMAGE_DOMAINS.split(',') : [])]
        domains: ['abbey-collections-images.s3.amazonaws.com', 'art-history-images.s3.amazonaws.com', ...(process.env.IMAGE_DOMAINS ? process.env.IMAGE_DOMAINS.split(',') : [])]
    },
    webpack: (config) => {
      // this will override the experiments
      config.experiments = { ...config.experiments, topLevelAwait: true };
      // this will just update topLevelAwait property of config.experiments
      // config.experiments.topLevelAwait = true 
      return config;
    },
}
