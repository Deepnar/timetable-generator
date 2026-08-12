"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Plus, Trash2, Loader2, RefreshCw, Play,
} from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiPost, apiPut } from "@/lib/api";
import {
  useProfile, useProfileResources, useProfileParameters,
  useRooms, useFaculty, useGroups, useSubjects,
  useHardConstraints, useSoftConstraints, useConstraintTypes,
  useGenerations,
} from "@/hooks/use-resources";
import type { Generation } from "@/lib/types";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const RESOURCE_TYPES: Record<string, { label: string }> = {
  ROOM: { label: "Rooms" },
  FACULTY: { label: "Faculty" },
  STUDENT_GROUP: { label: "Groups" },
  SUBJECT: { label: "Subjects" },
};

const PARAM_CATALOG: { key: string; type: string; label: string; hint: string }[] = [
  { key: "slot_duration_minutes", type: "INT", label: "Slot duration (min)", hint: "60" },
  { key: "slots_per_day", type: "INT", label: "Slots per day", hint: "7" },
  { key: "day_start_time", type: "STRING", label: "Day start", hint: "09:00" },
  { key: "working_days", type: "JSON", label: "Working days", hint: '["MON","TUE","WED","THU","FRI"]' },
  { key: "term_start", type: "STRING", label: "Term start", hint: "2026-07-20" },
  { key: "session_type", type: "STRING", label: "Session type", hint: "CLASS / EXAM" },
  { key: "lunch_break_after_slot", type: "INT", label: "Lunch after slot", hint: "3" },
  { key: "lunch_break_duration_minutes", type: "INT", label: "Lunch duration (min)", hint: "60" },
  { key: "allow_saturday", type: "BOOLEAN", label: "Allow Saturday", hint: "false" },
  { key: "buffer_slots_per_day", type: "INT", label: "Buffer slots/day", hint: "1" },
  { key: "max_room_utilization_pct", type: "FLOAT", label: "Max room utilization %", hint: "0.85" },
];

const SCOPE_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  DEPARTMENT: "neutral", YEAR: "info", DIVISION: "success", EVENT: "warning", EXAM: "danger",
};

const GENERATION_TONE: Record<string, "success" | "warning" | "info" | "danger" | "neutral"> = {
  PENDING: "warning", RUNNING: "info", COMPLETED: "success", FAILED: "danger", LOCKED: "neutral",
};

function isJSON(v: string) {
  try { JSON.parse(v); return true; } catch { return false; }
}

export default function ProfileDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const profileId = Number(params.id);
  const qc = useQueryClient();

  const profile = useProfile(profileId);
  const resources = useProfileResources(profileId);
  const parameters = useProfileParameters(profileId);
  const hard = useHardConstraints(profileId);
  const soft = useSoftConstraints(profileId);
  const types = useConstraintTypes();

  const roomsQ = useRooms({ limit: 1000 });
  const facultyQ = useFaculty({ limit: 1000 });
  const groupsQ = useGroups({ limit: 1000 });
  const subjectsQ = useSubjects({ limit: 1000 });
  const generations = useGenerations({ limit: 200 });

  const invalidateProfile = () => {
    qc.invalidateQueries({ queryKey: ["profile", profileId] });
    qc.invalidateQueries({ queryKey: ["profiles"] });
  };

  const [name, setName] = useState<string | null>(null);

  // ── Resource shuttle state ──────────────────────────────
  const [addingType, setAddingType] = useState<string>("");
  const [addingId, setAddingId] = useState("");

  // ── New parameter / constraint state ────────────────────
  const [newParamKey, setNewParamKey] = useState("");
  const [newParamValue, setNewParamValue] = useState("");
  const [newHardType, setNewHardType] = useState("");
  const [newSoftType, setNewSoftType] = useState("");

  const [saving, setSaving] = useState(false);

  const p = profile.data;
  const attachedByType = useMemo(() => {
    const map: Record<string, number[]> = { ROOM: [], FACULTY: [], STUDENT_GROUP: [], SUBJECT: [] };
    for (const r of resources.data ?? []) {
      if (r.resource_type in map) map[r.resource_type].push(r.resource_id);
    }
    return map;
  }, [resources.data]);

  const resourcePool: Record<string, { id: number; name: string }[]> = useMemo(() => {
    return {
      ROOM: (roomsQ.data?.rows ?? []).map((r) => ({ id: r.id, name: r.room_code })),
      FACULTY: (facultyQ.data?.rows ?? []).map((f) => ({ id: f.id, name: f.name })),
      STUDENT_GROUP: (groupsQ.data?.rows ?? []).map((g) => ({ id: g.id, name: g.name })),
      SUBJECT: (subjectsQ.data?.rows ?? []).map((s) => ({ id: s.id, name: `${s.subject_code} · ${s.name}` })),
    };
  }, [roomsQ.data, facultyQ.data, groupsQ.data, subjectsQ.data]);

  async function addResource(type: string) {
    if (!addingId) return;
    setSaving(true);
    try {
      await apiPost(`/api/v1/profiles/${profileId}/resources`, {
        resource_type: type, resource_id: Number(addingId),
      });
      toast.success("Resource added");
      invalidateProfile();
      setAddingId("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Add failed");
    } finally {
      setSaving(false);
    }
  }

  async function removeResource(type: string, resourceId: number) {
    const row = (resources.data ?? []).find(
      (r) => r.resource_type === type && r.resource_id === resourceId);
    if (!row) return;
    try {
      await apiDelete(`/api/v1/profiles/${profileId}/resources/${row.id}`);
      toast.success("Resource removed");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Remove failed");
    }
  }

  async function saveParameter(key: string, value: string, type: string) {
    try {
      await apiPost(`/api/v1/profiles/${profileId}/parameters`, {
        param_key: key, param_value: value, param_type: type,
      });
      toast.success("Parameter saved");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    }
  }

  async function deleteParameter(key: string) {
    try {
      await apiDelete(`/api/v1/profiles/${profileId}/parameters/${key}`);
      toast.success("Parameter removed");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function addHard() {
    if (!newHardType) return;
    setSaving(true);
    try {
      await apiPost("/api/v1/constraints/hard", {
        profile_id: profileId, constraint_type: newHardType,
      });
      toast.success("Hard constraint added");
      setNewHardType("");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Add failed");
    } finally {
      setSaving(false);
    }
  }

  async function addSoft() {
    if (!newSoftType) return;
    setSaving(true);
    try {
      await apiPost("/api/v1/constraints/soft", {
        profile_id: profileId, constraint_type: newSoftType, weight: 1,
      });
      toast.success("Soft constraint added");
      setNewSoftType("");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Add failed");
    } finally {
      setSaving(false);
    }
  }

  async function deleteHard(id: number) {
    try {
      await apiDelete(`/api/v1/constraints/hard/${id}`);
      toast.success("Hard constraint removed");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function deleteSoft(id: number) {
    try {
      await apiDelete(`/api/v1/constraints/soft/${id}`);
      toast.success("Soft constraint removed");
      invalidateProfile();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  }

  const runsForProfile = useMemo(
    () => (generations.data?.rows ?? []).filter((g) => g.profile_id === profileId),
    [generations.data, profileId],
  );

  const isLoading = profile.isLoading || resources.isLoading || parameters.isLoading;
  const isError = profile.isError || resources.isError || parameters.isError;

  return (
    <ProtectedShell>
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.push("/profiles")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1">
            {profile.isLoading ? (
              <Skeleton className="h-8 w-64" />
            ) : name !== null ? (
              <div className="flex items-center gap-2">
                <Input
                  className="display h-9 max-w-sm text-2xl"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={() => {
                    if (name && name !== p?.name) {
                      apiPut(`/api/v1/profiles/${profileId}`, {
                        ...pick(p), name,
                      }).then(() => {
                        toast.success("Profile renamed");
                        invalidateProfile();
                      }).catch((e) => toast.error(e instanceof Error ? e.message : "Rename failed"));
                    }
                    setName(null);
                  }}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                />
              </div>
            ) : (
              <h1
                className="display cursor-pointer text-3xl text-ink hover:underline"
                onClick={() => p && setName(p.name)}
                title="Click to rename"
              >
                {p?.name}
              </h1>
            )}
            <p className="mt-0.5 text-sm text-muted-foreground">
              {p?.academic_year}{p?.semester ? ` · Sem ${p.semester}` : ""}{p?.department ? ` · ${p.department}` : ""}
            </p>
          </div>
          {p && (
            <div className="flex items-center gap-2">
              <Badge variant={SCOPE_TONE[p.scope_type] ?? "neutral"}>{p.scope_type}</Badge>
              <Badge variant={p.is_active ? "success" : "neutral"}>{p.is_active ? "Active" : "Inactive"}</Badge>
              <Button onClick={() => router.push(`/generate?profile=${profileId}`)}>
                <Play className="mr-1 h-4 w-4" /> Generate
              </Button>
            </div>
          )}
        </div>

        {isError && <ErrorBanner message="Failed to load profile" />}

        <div className="rounded-md border bg-surface shadow-sm">
          <Tabs defaultValue="resources">
            <div className="border-b px-4 pt-3">
              <TabsList>
                <TabsTrigger value="resources">Resources</TabsTrigger>
                <TabsTrigger value="parameters">Parameters</TabsTrigger>
                <TabsTrigger value="constraints">Constraints</TabsTrigger>
                <TabsTrigger value="runs">Runs</TabsTrigger>
              </TabsList>
            </div>

            <div className="p-5">
              {/* ── Resources ─────────────────────────────── */}
              <TabsContent value="resources">
                {isLoading ? (
                  <div className="space-y-2"><Skeleton className="h-40" /></div>
                ) : (
                  <div className="grid gap-6 lg:grid-cols-2">
                    {Object.entries(RESOURCE_TYPES).map(([type, cfg]) => {
                      const attached = attachedByType[type] ?? [];
                      const available = (resourcePool[type] ?? []).filter(
                        (r) => !attached.includes(r.id));
                      return (
                        <div key={type} className="rounded-md border p-4">
                          <div className="mb-3 flex items-center justify-between">
                            <h3 className="eyebrow">{cfg.label}</h3>
                            <Badge variant="neutral">{attached.length} attached</Badge>
                          </div>
                          <ul className="mb-3 max-h-56 space-y-1 overflow-y-auto">
                            {attached.length === 0 && (
                              <li className="text-sm text-muted-foreground">None yet.</li>
                            )}
                            {attached.map((id) => {
                              const item = (resourcePool[type] ?? []).find((r) => r.id === id);
                              return (
                                <li key={id} className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-1.5 text-sm">
                                  <span className="truncate text-ink">{item?.name ?? `#${id}`}</span>
                                  <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" onClick={() => removeResource(type, id)}>
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </li>
                              );
                            })}
                          </ul>
                          <div className="flex gap-2">
                            <Select value={addingType === type ? addingId : ""} onValueChange={setAddingId}>
                              <SelectTrigger className="h-8 flex-1"><SelectValue placeholder="Add…" /></SelectTrigger>
                              <SelectContent>
                                {available.map((r) => (
                                  <SelectItem key={r.id} value={String(r.id)}>{r.name}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8"
                              disabled={!addingId || saving}
                              onClick={() => { setAddingType(type); addResource(type); }}
                            >
                              <Plus className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              {/* ── Parameters ────────────────────────────── */}
              <TabsContent value="parameters">
                <div className="space-y-3">
                  {parameters.data?.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No parameters yet. Add from the catalog below — or leave defaults for the solver.
                    </p>
                  )}
                  {parameters.data?.map((param) => (
                    <div key={param.param_key} className="flex items-center gap-2 rounded-md border px-3 py-2">
                      <span className="w-52 shrink-0 font-mono text-xs font-medium text-ink">{param.param_key}</span>
                      <Badge variant="neutral" className="shrink-0">{param.param_type}</Badge>
                      <Input
                        className="h-8 flex-1"
                        defaultValue={param.param_value}
                        onBlur={(e) => {
                          if (e.target.value !== param.param_value) {
                            saveParameter(param.param_key, e.target.value, param.param_type);
                          }
                        }}
                      />
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => deleteParameter(param.param_key)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}

                  <div className="flex items-center gap-2 rounded-md border border-dashed px-3 py-2">
                    <Select value={newParamKey} onValueChange={setNewParamKey}>
                      <SelectTrigger className="h-8 w-60"><SelectValue placeholder="Pick a parameter…" /></SelectTrigger>
                      <SelectContent>
                        {PARAM_CATALOG.map((c) => (
                          <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      className="h-8 flex-1"
                      placeholder={PARAM_CATALOG.find((c) => c.key === newParamKey)?.hint ?? "value"}
                      value={newParamValue}
                      onChange={(e) => setNewParamValue(e.target.value)}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8"
                      disabled={!newParamKey || !newParamValue}
                      onClick={() => {
                        const cat = PARAM_CATALOG.find((c) => c.key === newParamKey);
                        if (!cat) return;
                        if (cat.type === "JSON" && !isJSON(newParamValue)) {
                          toast.error("Value must be valid JSON");
                          return;
                        }
                        saveParameter(newParamKey, newParamValue, cat.type);
                        setNewParamKey("");
                        setNewParamValue("");
                      }}
                    >
                      <Plus className="h-4 w-4" /> Add
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* ── Constraints ───────────────────────────── */}
              <TabsContent value="constraints">
                <div className="grid gap-6 lg:grid-cols-2">
                  <div>
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="eyebrow">Hard constraints</h3>
                      <Badge variant="neutral">{hard.data?.rows.length ?? 0}</Badge>
                    </div>
                    <ul className="space-y-1.5">
                      {(hard.data?.rows ?? []).map((c) => (
                        <li key={c.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                          <div className="min-w-0">
                            <p className="font-mono text-xs font-medium text-ink">{c.constraint_type}</p>
                            {c.description && <p className="truncate text-xs text-muted-foreground">{c.description}</p>}
                          </div>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => deleteHard(c.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </li>
                      ))}
                      {(hard.data?.rows ?? []).length === 0 && (
                        <li className="text-sm text-muted-foreground">No profile-level hard constraints.</li>
                      )}
                    </ul>
                    <div className="mt-3 flex gap-2">
                      <Select value={newHardType} onValueChange={setNewHardType}>
                        <SelectTrigger className="h-8 flex-1"><SelectValue placeholder="Add a hard constraint…" /></SelectTrigger>
                        <SelectContent>
                          {(types.data?.hard ?? []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button variant="outline" size="sm" className="h-8" disabled={!newHardType || saving} onClick={addHard}>
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  <div>
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="eyebrow">Soft constraints</h3>
                      <Badge variant="neutral">{soft.data?.rows.length ?? 0}</Badge>
                    </div>
                    <ul className="space-y-1.5">
                      {(soft.data?.rows ?? []).map((c) => (
                        <li key={c.id} className="rounded-md border px-3 py-2 text-sm">
                          <div className="flex items-center justify-between">
                            <p className="font-mono text-xs font-medium text-ink">{c.constraint_type}</p>
                            <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" onClick={() => deleteSoft(c.id)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                          <div className="mt-1.5 flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Weight</span>
                            <Input
                              type="number"
                              step={0.1}
                              min={0}
                              max={10}
                              defaultValue={c.weight}
                              className="h-7 w-20"
                              onBlur={(e) => {
                                const v = Number(e.target.value);
                                if (v !== c.weight) {
                                  apiPut(`/api/v1/constraints/soft/${c.id}`, {
                                    profile_id: profileId,
                                    constraint_type: c.constraint_type,
                                    weight: v,
                                  }).then(() => {
                                    toast.success("Weight updated");
                                    invalidateProfile();
                                  }).catch((err) => toast.error(err instanceof Error ? err.message : "Update failed"));
                                }
                              }}
                            />
                          </div>
                        </li>
                      ))}
                      {(soft.data?.rows ?? []).length === 0 && (
                        <li className="text-sm text-muted-foreground">No profile-level soft constraints.</li>
                      )}
                    </ul>
                    <div className="mt-3 flex gap-2">
                      <Select value={newSoftType} onValueChange={setNewSoftType}>
                        <SelectTrigger className="h-8 flex-1"><SelectValue placeholder="Add a soft constraint…" /></SelectTrigger>
                        <SelectContent>
                          {(types.data?.soft ?? []).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button variant="outline" size="sm" className="h-8" disabled={!newSoftType || saving} onClick={addSoft}>
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* ── Runs ──────────────────────────────────── */}
              <TabsContent value="runs">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="eyebrow">Generation runs for this profile</h3>
                  <Button variant="ghost" size="sm" onClick={() => generations.refetch()}>
                    <RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh
                  </Button>
                </div>
                {runsForProfile.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No runs yet. Hit Generate to create one.</p>
                ) : (
                  <ul className="divide-y divide-border">
                    {runsForProfile.map((g) => (
                      <RunRow key={g.id} run={g} onOpen={() => router.push(`/instances/${g.id}`)} />
                    ))}
                  </ul>
                )}
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </ProtectedShell>
  );
}

function RunRow({ run, onOpen }: { run: Generation; onOpen: () => void }) {
  return (
    <li className="flex items-center justify-between py-2.5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink">Run #{run.id}</span>
          <Badge variant={GENERATION_TONE[run.generation_status] ?? "neutral"}>{run.generation_status}</Badge>
          {run.placement_warning && <span className="truncate text-xs text-warning">{run.placement_warning}</span>}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {run.algorithm_used} · {run.variation} · {run.instances_produced}/{run.instances_requested} instances
          {run.run_duration_ms != null && ` · ${(run.run_duration_ms / 1000).toFixed(1)}s`}
        </p>
      </div>
      {run.generation_status === "COMPLETED" && (
        <Button variant="link" size="sm" onClick={onOpen}>View instances →</Button>
      )}
    </li>
  );
}

function pick(p: { name: string; description: string | null; scope_type: string; academic_year: string; semester: number | null; department: string | null } | undefined) {
  return {
    name: p?.name ?? "",
    description: p?.description ?? null,
    scope_type: p?.scope_type ?? "DIVISION",
    academic_year: p?.academic_year ?? "2026-27",
    semester: p?.semester,
    department: p?.department,
  };
}
