/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ['./src/**/*.html', './build.mjs', './assets/site.js'],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                // The app's MUI theme: primary #d52728, secondary #212121
                brand: { DEFAULT: '#d52728', dark: '#a91d1e', soft: '#fdecec' },
                ink: '#212121',
            },
            fontFamily: {
                sans: ['Roboto', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                mono: ['"Roboto Mono"', 'ui-monospace', 'monospace'],
            },
            typography: ({ theme }) => ({
                DEFAULT: {
                    css: {
                        '--tw-prose-links': theme('colors.brand.DEFAULT'),
                        '--tw-prose-invert-links': '#f87171',
                        a: { fontWeight: '500' },
                        'code::before': { content: 'none' },
                        'code::after': { content: 'none' },
                        code: { fontWeight: '500' },
                    },
                },
            }),
        },
    },
    plugins: [require('@tailwindcss/typography')],
};
