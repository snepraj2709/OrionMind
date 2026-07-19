const config = {
  '*.{js,jsx,ts,tsx,mjs,cjs}': ['eslint --fix', 'prettier --write'],
  '*.{css,json,md,yaml,yml}': 'prettier --write',
};

export default config;
