"use client";

import { createTheme } from "@mui/material/styles";

export const mono =
  "var(--font-geist-mono),'SF Mono',ui-monospace,Menlo,Consolas,monospace";

// CSS custom properties (not theme.palette.chart.* via useTheme()) so chart
// colors resolve correctly - light/dark included - without every component
// that draws a sparkline needing to render inside this app's ThemeProvider
// (e.g. in isolated component tests).
export const chartColors = {
  cpu: "var(--mui-palette-chart-cpu)",
  mem: "var(--mui-palette-chart-mem)",
  views: "var(--mui-palette-chart-views)",
  viewers: "var(--mui-palette-chart-viewers)",
};

interface ChartPalette {
  cpu: string;
  mem: string;
  views: string;
  viewers: string;
}

declare module "@mui/material/styles" {
  interface Palette {
    chart: ChartPalette;
  }
  interface PaletteOptions {
    chart?: ChartPalette;
  }
}

const theme = createTheme({
  cssVariables: { colorSchemeSelector: "class" },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: "#d93b2b" },
        background: { default: "#fafafa" },
        chart: { cpu: "#2a78d6", mem: "#4a3aa7", views: "#1baf7a", viewers: "#eb6834" },
      },
    },
    dark: {
      palette: {
        primary: { main: "#ff6b5e" },
        background: { default: "#0f1214", paper: "#16191c" },
        chart: { cpu: "#3987e5", mem: "#9085e9", views: "#1baf7a", viewers: "#eb6834" },
      },
    },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily:
      "var(--font-geist-sans),Roboto,'Helvetica Neue',Arial,sans-serif",
    h5: { fontWeight: 650 },
    h6: { fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiCard: {
      defaultProps: { variant: "outlined" },
    },
    MuiAppBar: {
      styleOverrides: { root: { backgroundImage: "none" } },
    },
  },
});

export default theme;
