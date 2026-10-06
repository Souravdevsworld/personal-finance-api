/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'] },
      colors: {
        ink: '#12171f',
        gain: { DEFAULT: '#0f8a5f', soft: '#e6f4ee' },
        loss: { DEFAULT: '#c2410c', soft: '#fdeee6' },
      },
    },
  },
  plugins: [],
}
