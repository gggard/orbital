"use client";

import { createTheme } from "@mui/material/styles";

export const mono =
  "var(--font-geist-mono),'SF Mono',ui-monospace,Menlo,Consolas,monospace";

const theme = createTheme({
  cssVariables: { colorSchemeSelector: "class" },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: "#d93b2b" },
        background: { default: "#fafafa" },
      },
    },
    dark: {
      palette: {
        primary: { main: "#ff6b5e" },
        background: { default: "#0f1214", paper: "#16191c" },
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
