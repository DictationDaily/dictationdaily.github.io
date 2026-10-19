/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ['./*.html'],
    darkMode: 'media',
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
        },
    },
    plugins: [],
};
