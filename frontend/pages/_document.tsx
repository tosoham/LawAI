/**
 * Custom Document
 *
 * Exists for one reason: applying the saved theme before first paint. See
 * THEME_INIT_SCRIPT for why that has to happen outside React.
 */

import Document, { Head, Html, Main, NextScript } from 'next/document';
import { THEME_INIT_SCRIPT } from '@/lib/theme';

export default class LawAIDocument extends Document {
  render() {
    return (
      <Html lang="en">
        <Head>
          <meta name="theme-color" content="#1e3a5f" />
        </Head>
        <body>
          {/* eslint-disable-next-line react/no-danger */}
          <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
          <Main />
          <NextScript />
        </body>
      </Html>
    );
  }
}
