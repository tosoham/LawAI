/**
 * Registers @testing-library/jest-dom's custom matchers with TypeScript.
 *
 * jest.setup.js requires the package at runtime, but that is a plain .js file so
 * tsc never sees it and `expect(...).toBeInTheDocument()` fails to type-check.
 * This side-effect import pulls in the matcher declarations for the whole
 * project.
 */
import '@testing-library/jest-dom';
