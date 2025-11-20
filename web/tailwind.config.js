/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            keyframes: {
                'progress-stripes': {
                    '0%': { backgroundPosition: '1rem 0' },
                    '100%': { backgroundPosition: '0 0' },
                }
            }
        },
    },
    plugins: [],
}
