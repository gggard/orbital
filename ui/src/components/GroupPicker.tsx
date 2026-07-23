"use client";

import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import { useEffect, useState } from "react";
import { useGroups } from "@/lib/api";

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/**
 * Multi-select group picker backed by the known-groups directory
 * (GET /api/v1/groups). Typing filters: instantly client-side, and — after a
 * short debounce — server-side too, so directories larger than one response
 * page stay searchable. Free-typed group names are still accepted.
 */
export default function GroupPicker({
  value,
  onChange,
  label,
  helperText,
  extraOptions = [],
}: {
  value: string[];
  onChange: (groups: string[]) => void;
  label: string;
  helperText?: string;
  extraOptions?: string[];
}) {
  const [input, setInput] = useState("");
  const q = useDebounced(input, 250);
  const { data } = useGroups(q);
  const options = [...new Set([...(data?.groups ?? []), ...extraOptions])].sort((a, b) =>
    a.localeCompare(b),
  );

  return (
    <Autocomplete
      multiple
      freeSolo
      options={options}
      value={value}
      onChange={(_, v) => onChange(v as string[])}
      inputValue={input}
      onInputChange={(_, v) => setInput(v)}
      renderInput={(params) => (
        <TextField {...params} size="small" label={label} helperText={helperText} />
      )}
    />
  );
}
