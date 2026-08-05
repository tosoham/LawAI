// next/jest wires up the SWC transform, CSS/asset stubs and the tsconfig path
// aliases (@/*), so tests import modules exactly as the app does.
const nextJest = require('next/jest');

const createJestConfig = nextJest({ dir: './' });

/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'jest-environment-jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testPathIgnorePatterns: ['/node_modules/', '/.next/'],
  // `output: 'standalone'` copies package.json into .next/standalone, which
  // jest-haste-map then sees as a second module of the same name. Excluding it
  // from the module map (testPathIgnorePatterns only covers test discovery)
  // silences the collision warning.
  modulePathIgnorePatterns: ['<rootDir>/.next/'],
  collectCoverageFrom: [
    'lib/**/*.{ts,tsx}',
    'components/**/*.{ts,tsx}',
    'hooks/**/*.{ts,tsx}',
  ],
};

module.exports = createJestConfig(config);
