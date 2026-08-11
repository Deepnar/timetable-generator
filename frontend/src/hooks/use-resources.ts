"use client";

import { useQuery, useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiList, apiPost, apiPut, apiDelete, type ListParams } from "@/lib/api";
import type {
  Room, Faculty, StudentGroup, Subject, Generation, Instance, Slot, Me, Profile,
} from "@/lib/types";

// Query keys
export const qk = {
  rooms: (p: ListParams) => ["rooms", p] as const,
  faculty: (p: ListParams) => ["faculty", p] as const,
  groups: (p: ListParams) => ["groups", p] as const,
  subjects: (p: ListParams) => ["subjects", p] as const,
  generations: (p: ListParams) => ["generations", p] as const,
  generationStatus: (id: number) => ["generation", id, "status"] as const,
  instances: (generationId: number) => ["instances", generationId] as const,
  allInstances: (p: ListParams) => ["instances", p] as const,
  instanceSlots: (instanceId: number) => ["instance", instanceId, "slots"] as const,
  me: () => ["me"] as const,
  profiles: (p: ListParams) => ["profiles", p] as const,
};

// Resources
export function useRooms(params: ListParams) {
  return useQuery({ queryKey: qk.rooms(params), queryFn: () => apiList<Room>("/api/v1/rooms", params) });
}
export function useFaculty(params: ListParams) {
  return useQuery({ queryKey: qk.faculty(params), queryFn: () => apiList<Faculty>("/api/v1/faculty", params) });
}
export function useGroups(params: ListParams) {
  return useQuery({ queryKey: qk.groups(params), queryFn: () => apiList<StudentGroup>("/api/v1/groups", params) });
}
export function useSubjects(params: ListParams) {
  return useQuery({ queryKey: qk.subjects(params), queryFn: () => apiList<Subject>("/api/v1/subjects", params) });
}

// Generations + instances
export function useGenerations(params: ListParams) {
  return useQuery({ queryKey: qk.generations(params), queryFn: () => apiList<Generation>("/api/v1/generate", params) });
}
export function useGenerationStatus(id: number | null | undefined) {
  return useQuery({
    queryKey: qk.generationStatus(id ?? -1),
    queryFn: () => apiGet<Generation>(`/api/v1/generate/${id}/status`),
    enabled: id != null,
    refetchInterval: (query) => {
      const s = query.state.data?.generation_status;
      return s === "PENDING" || s === "RUNNING" ? 2000 : false;
    },
  });
}
export function useInstances(generationId: number | null | undefined) {
  return useQuery({
    queryKey: qk.instances(generationId ?? -1),
    queryFn: () => apiList<Instance>(`/api/v1/instances/${generationId}`),
    enabled: generationId != null,
  });
}
export function useAllInstances(params: ListParams) {
  return useQuery({ queryKey: qk.allInstances(params), queryFn: () => apiList<Instance>("/api/v1/instances", params) });
}
export function useInstanceSlots(instanceId: number | null | undefined) {
  return useQuery({
    queryKey: qk.instanceSlots(instanceId ?? -1),
    queryFn: () => apiGet<Slot[]>(`/api/v1/instances/${instanceId}/slots`),
    enabled: instanceId != null,
  });
}

// Identity
export function useMe() {
  return useQuery({ queryKey: qk.me(), queryFn: () => apiGet<Me>("/auth/me"), staleTime: 60_000 });
}

// Profiles
export function useProfiles(params: ListParams) {
  return useQuery({ queryKey: qk.profiles(params), queryFn: () => apiList<Profile>("/api/v1/profiles", params) });
}

// Mutations (CRUD)
export function useCreateResource<T>(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<T>(path, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [path.split("/").pop()] }),
  });
}
export function useUpdateResource<T>(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) =>
      apiPut<T>(`${path}/${id}`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: [path.split("/").pop()] }),
  });
}
export function useDeleteResource(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete(`${path}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [path.split("/").pop()] }),
  });
}

// Optimistic slot override
export function useSlotOverride(instanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slotId, payload }: { slotId: number; payload: Record<string, unknown> }) =>
      apiPut(`/api/v1/instances/${instanceId}/slots/${slotId}`, payload),
    onMutate: async ({ slotId, payload }) => {
      await qc.cancelQueries({ queryKey: qk.instanceSlots(instanceId) });
      const prev = qc.getQueryData<Slot[]>(qk.instanceSlots(instanceId));
      qc.setQueryData<Slot[]>(qk.instanceSlots(instanceId), (old) =>
        old?.map((s) => (s.id === slotId ? { ...s, ...payload } : s)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.instanceSlots(instanceId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: qk.instanceSlots(instanceId) }),
  });
}

// Facet counts for the drill-down navigation. Probes each facet value with a
// tiny limit=1 request and reads X-Total-Count, so the tiles/rail show true
// totals (not just the current page). Counts respect the active drill filters
// EXCEPT the facet's own dimension, so switching a branch is one click.
export function useFacetCounts<T>(path: string, facetName: string, values: string[], active: ListParams) {
  return useQueries({
    queries: values.map((value) => ({
      queryKey: ["facet", path, facetName, value, active] as const,
      queryFn: () => apiList<T>(path, { ...active, [facetName]: value, limit: 1 }),
      staleTime: 30_000,
    })),
  });
}
