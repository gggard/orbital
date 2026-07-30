"use client";

import AdminPanelSettingsOutlinedIcon from "@mui/icons-material/AdminPanelSettingsOutlined";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";
import LoginIcon from "@mui/icons-material/Login";
import LogoutIcon from "@mui/icons-material/Logout";
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
    <Box
      component={Link}
      href="/admin"
      aria-label="admin dashboard"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        color: "text.secondary",
        textDecoration: "none",
        fontSize: 13,
        fontWeight: 600,
        px: 1.25,
        py: 0.75,
        borderRadius: 1,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <AdminPanelSettingsOutlinedIcon sx={{ fontSize: 17 }} />
      Admin
    </Box>
  );
}

function UserMenuDivider() {
  const { data: me } = useMe();
  if (!me || !me.auth_enabled) return null;
  return <Box sx={{ width: "1px", height: 22, bgcolor: "divider", mx: 0.5 }} />;
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

function userInitials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]/).filter(Boolean);
  const chars = parts.length > 1 ? [parts[0][0], parts[1][0]] : [name[0]];
  return chars.join("").toUpperCase() || "?";
}

function UserMenu() {
  const { data: me } = useMe();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  if (!me || !me.auth_enabled) return null;
  return (
    <>
      <Tooltip title={me.email}>
        <IconButton size="small" onClick={(e) => setAnchor(e.currentTarget)} aria-label="account">
          <Avatar sx={{ width: 26, height: 26, fontSize: "0.72rem", bgcolor: "action.selected", color: "primary.main" }}>
            {userInitials(me.email)}
          </Avatar>
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
        <MenuItem disabled sx={{ opacity: "1 !important" }}>
          <Stack>
            <Typography variant="body2">{me.email}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: "capitalize" }}>
              {me.role} · {me.groups.join(", ") || "no groups"}
            </Typography>
          </Stack>
        </MenuItem>
        <MenuItem component={Link} href="/tokens" onClick={() => setAnchor(null)}>
          <KeyOutlinedIcon fontSize="small" sx={{ mr: 1 }} /> My tokens
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

function AuthGate({ children }: { readonly children: React.ReactNode }) {
  const { data: me, error, isLoading } = useMe();
  const pathname = usePathname();

  if (isLoading) return <Skeleton variant="rounded" height={240} />;

  if (error?.status === 401)
    return (
      <Stack spacing={2} sx={{ alignItems: "center", py: 12 }}>
        <Logo size={72} variant="tile" />
        <Typography
          variant="h5"
          sx={{
            letterSpacing: "-0.015em",
            backgroundImage: "linear-gradient(115deg, #ff7060, #c22718)",
            backgroundClip: "text",
            WebkitBackgroundClip: "text",
            color: "transparent",
          }}
        >
          Orbital
        </Typography>
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

export default function AppShell({ children }: { readonly children: React.ReactNode }) {
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
            sx={{
              fontWeight: 750,
              letterSpacing: "-0.01em",
              textDecoration: "none",
              backgroundImage: "linear-gradient(115deg, #ff7060, #c22718)",
              backgroundClip: "text",
              WebkitBackgroundClip: "text",
              color: "transparent",
            }}
          >
            Orbital
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <ThemeToggle />
          <AdminLink />
          <UserMenuDivider />
          <UserMenu />
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <AuthGate>{children}</AuthGate>
      </Container>
    </>
  );
}
