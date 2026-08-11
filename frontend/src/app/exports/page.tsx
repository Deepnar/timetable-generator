"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { useAllInstances } from "@/hooks/use-resources";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const FORMATS = [
  { ext: "pdf", label: "PDF", desc: "Grid layout, per-group pages" },
  { ext: "csv", label: "CSV", desc: "Row-per-slot spreadsheet" },
  { ext: "ical", label: "iCal", desc: "Weekly-recurring calendar (import into Google/Outlook)" },
];

export default function ExportsPage() {
  const instances = useAllInstances({ limit: 200 });
  const [instanceId, setInstanceId] = useState("");
  const [format, setFormat] = useState("pdf");

  async function download() {
    if (!instanceId) return;
    try {
      const token = typeof window !== "undefined" ? window.localStorage.getItem("timetable_token") : null;
      const res = await fetch(`http://localhost:8000/api/v1/export/instances/${instanceId}/${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(res.statusText);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `instance-${instanceId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Download started");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  return (
    <ProtectedShell>
      <div className="max-w-2xl">
        <h1 className="display text-3xl text-ink">Exports</h1>
        <p className="mt-1 text-sm text-muted-foreground">Download a timetable in PDF, CSV, or iCal.</p>

        <div className="mt-6 rounded-md border bg-surface p-6 shadow-sm">
          <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="instance">Instance</Label>
              <Select value={instanceId} onValueChange={setInstanceId}>
                <SelectTrigger id="instance" className="w-full">
                  <SelectValue placeholder="Select an instance…" />
                </SelectTrigger>
                <SelectContent>
                  {(instances.data?.rows ?? []).map((inst) => (
                    <SelectItem key={inst.id} value={String(inst.id)}>
                      Instance #{inst.id} · {inst.status} · gen {inst.generation_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Format</Label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {FORMATS.map((f) => (
                  <button
                    key={f.ext}
                    onClick={() => setFormat(f.ext)}
                    className={`flex flex-col items-start gap-1 rounded-md border p-4 text-left transition-colors ${
                      format === f.ext ? "border-primary bg-accent" : "border-border bg-surface hover:shadow-sm"
                    }`}
                  >
                    <span className={`text-sm font-semibold ${format === f.ext ? "text-accent-foreground" : "text-ink"}`}>{f.label}</span>
                    <span className="text-xs text-muted-foreground">{f.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            <Button onClick={download} disabled={!instanceId} className="w-full">
              <Download className="mr-1 h-4 w-4" /> Download
            </Button>
          </div>
        </div>

        <p className="mt-4 text-sm text-muted-foreground">
          Tip: exports also accept <code className="font-mono text-xs">?faculty_id=</code>,{" "}
          <code className="font-mono text-xs">?group_id=</code>,{" "}
          <code className="font-mono text-xs">?year=</code> and{" "}
          <code className="font-mono text-xs">?department=</code> — a teacher can pull their own
          schedule directly (the teacher portal wiring is in the roadmap).
        </p>
      </div>
    </ProtectedShell>
  );
}
