/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ['./src/**/*.html', './build.mjs', './assets/site.js'],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                // The app's design tokens (dictationdaily.com
                // app/components/ui/tokens.ts): brand red for actions,
                // orange for streaks, warm greys
                brand: { DEFAULT: '#d52728', dark: '#9e1b1c', soft: '#ffedea' },
                flame: { DEFAULT: '#ff8a00', dark: '#c45f00', text: '#a34c00', soft: '#fff1e3', line: '#f8dcbe' },
                gold: '#ffc233',
                ink: '#1f1a17',
                cream: '#fff6f1',
                // Warm greys instead of Tailwind's cool ones, so every
                // existing gray-* class matches the app
                gray: {
                    50: '#fffcfa',
                    100: '#f6eee9',
                    200: '#f0e4dc',
                    300: '#e2d3c9',
                    400: '#a79a91',
                    500: '#6b625c',
                    600: '#574e48',
                    700: '#4a423d',
                    800: '#2c2522',
                    900: '#231d1a',
                    950: '#1a1512',
                },
            },
            fontFamily: {
                sans: ['Nunito', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                display: ['Fredoka', 'Nunito', 'ui-sans-serif', 'sans-serif'],
                mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
            },
            boxShadow: {
                // The app's pressable bottom edge
                edge: '0 4px 0 #e9ddd5',
                'edge-red': '0 4px 0 #9e1b1c',
                'edge-card': '0 6px 0 #f0e4dc',
            },
            typography: ({ theme }) => ({
                DEFAULT: {
                    css: {
                        '--tw-prose-links': theme('colors.brand.DEFAULT'),
                        '--tw-prose-invert-links': '#ff8a7a',
                        '--tw-prose-headings': theme('colors.ink'),
                        '--tw-prose-body': theme('colors.gray.700'),
                        a: { fontWeight: '700' },
                        'h1, h2, h3, h4': { fontFamily: theme('fontFamily.display').join(', '), fontWeight: '700' },
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
