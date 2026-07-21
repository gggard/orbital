"use client";

import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import { useEffect, useState } from "react";
import { useTags } from "@/lib/api";

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/**
 * Multi-select tag picker backed by the known-tags directory
 * (GET /api/v1/tags, collected from apps visible to the caller). Typing
 * filters client-side instantly and, after a short debounce, server-side too.
 * Free-typed tags are always accepted — press Enter or comma to add one that
 * doesn't exist yet.
 */
export default function TagPicker({
  value,
  onChange,
  label = "Tags",
  helperText,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
  label?: string;
  helperText?: string;
}) {
  const [input, setInput] = useState("");
  const q = useDebounced(input, 250);
  const { data } = useTags(q);
  const options = [...new Set([...(data?.tags ?? []), ...value])].sort();

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
        <TextField
          {...params}
          size="small"
          label={label}
          placeholder={value.length ? undefined : "type to search or add…"}
          helperText={helperText}
        />
      )}
    />
  );
}
