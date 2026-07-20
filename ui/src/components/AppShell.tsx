"use client";

import AdminPanelSettingsOutlinedIcon from "@mui/icons-material/AdminPanelSettingsOutlined";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import LoginIcon from "@mui/icons-material/Login";
import LogoutIcon from "@mui/icons-material/Logout";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useColorScheme } from "@mui/material/styles";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import Logo from "@/components/Logo";
import { loginUrl, logout, useMe } from "@/lib/api";

function AdminLink() {
  const { data: me } = useMe();
  if (me?.role !== "admin") return null;
  return (
    <Tooltip title="Admin">
      <IconButton component={Link} href="/admin" color="inherit" aria-label="admin dashboard">
        <AdminPanelSettingsOutlinedIcon />
      </IconButton>
    </Tooltip>
  );
}

function ThemeToggle() {
  const { mode, setMode } = useColorScheme();
  const dark = mode === "dark";
  return (
    <Tooltip title={dark ? "Light mode" : "Dark mode"}>
      <IconButton
        color="inherit"
        onClick={() => setMode(dark ? "light" : "dark")}
        aria-label="toggle color scheme"
      >
        {dark ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
      </IconButton>
    </Tooltip>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  if (!me || !me.auth_enabled) return null;
  return (
    <>
      <Chip size="small" label={me.role} variant="outlined" sx={{ mr: 1, textTransform: "capitalize" }} />
      <IconButton size="small" onClick={(e) => setAnchor(e.currentTarget)} aria-label="account">
        <Avatar sx={{ width: 28, height: 28, fontSize: "0.8rem", bgcolor: "primary.main" }}>
          {(me.email[0] ?? "?").toUpperCase()}
        </Avatar>
      </IconButton>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        <MenuItem disabled sx={{ opacity: "1 !important" }}>
          <Stack>
            <Typography variant="body2">{me.email}</Typography>
            <Typography variant="caption" color="text.secondary">
              {me.groups.join(", ") || "no groups"}
            </Typography>
          </Stack>
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchor(null);
            logout();
          }}
        >
          <LogoutIcon fontSize="small" sx={{ mr: 1 }} /> Sign out
        </MenuItem>
      </Menu>
    </>
  );
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const { data: me, error, isLoading } = useMe();
  const pathname = usePathname();

  if (isLoading) return <Skeleton variant="rounded" height={240} />;

  if (error?.status === 401)
    return (
      <Stack spacing={2} sx={{ alignItems: "center", py: 12 }}>
        <Logo size={72} variant="tile" />
        <Typography variant="h5">Orbital</Typography>
        <Typography color="text.secondary">
          Sign in with your organization account to manage apps.
        </Typography>
        <Button variant="contained" size="large" startIcon={<LoginIcon />} href={loginUrl(pathname)}>
          Sign in
        </Button>
      </Stack>
    );

  if (error?.status === 403)
    return (
      <Stack spacing={2} sx={{ alignItems: "center", py: 12 }}>
        <Alert severity="warning" sx={{ maxWidth: 480 }}>
          You are signed in, but none of your groups grant access to this console.
          Ask an administrator to add you to an authorized group.
        </Alert>
        <Button onClick={() => logout()}>Sign in as a different user</Button>
      </Stack>
    );

  if (error)
    return (
      <Alert severity="error" sx={{ mt: 4 }}>
        control plane unreachable: {error.message}
      </Alert>
    );

  return <>{me && children}</>;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AppBar
        position="sticky"
        elevation={0}
        color="transparent"
        sx={{
          borderBottom: 1,
          borderColor: "divider",
          backdropFilter: "blur(8px)",
        }}
      >
        <Toolbar variant="dense" sx={{ gap: 1.5 }}>
          <Logo size={22} />
          <Typography
            component={Link}
            href="/"
            variant="subtitle1"
            color="inherit"
            sx={{ fontWeight: 700, textDecoration: "none" }}
          >
            Orbital
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <AdminLink />
          <UserMenu />
          <ThemeToggle />
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <AuthGate>{children}</AuthGate>
      </Container>
    </>
  );
}
