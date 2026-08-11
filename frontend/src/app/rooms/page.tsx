"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { ResourcePage, type FieldConfig } from "@/components/ResourcePage";
import { ProtectedShell } from "@/components/ProtectedShell";
import { Badge } from "@/components/ui/badge";
import { useRooms } from "@/hooks/use-resources";
import type { Room } from "@/lib/types";

const ROOM_TYPES = ["CLASSROOM", "LAB", "SEMINAR_HALL", "AUDITORIUM", "CUSTOM"];

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "room_code", label: "Room code", type: "text", required: true },
  { name: "room_type", label: "Room type", type: "select", options: ROOM_TYPES, required: true },
  { name: "capacity", label: "Capacity", type: "number", required: true, min: 0 },
  { name: "building", label: "Building", type: "text" },
  { name: "floor", label: "Floor", type: "number", min: 0 },
  { name: "has_projector", label: "Projector", type: "switch" },
  { name: "has_ac", label: "Air conditioned", type: "switch" },
];

const ROOM_TONES: Record<string, "info" | "success" | "warning" | "neutral"> = {
  CLASSROOM: "info",
  LAB: "success",
  SEMINAR_HALL: "warning",
  AUDITORIUM: "neutral",
  CUSTOM: "neutral",
};

const columns: ColumnDef<Room, unknown>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => <span className="font-medium text-ink">{row.original.name}</span>,
  },
  {
    accessorKey: "room_code",
    header: "Code",
    cell: ({ row }) => <span className="font-mono text-xs text-muted-foreground">{row.original.room_code}</span>,
  },
  {
    accessorKey: "room_type",
    header: "Type",
    cell: ({ row }) => (
      <Badge variant={ROOM_TONES[row.original.room_type] ?? "neutral"}>
        {row.original.room_type.replace("_", " ")}
      </Badge>
    ),
  },
  {
    accessorKey: "capacity",
    header: "Capacity",
    meta: { align: "right" },
    cell: ({ row }) => <span className="tabular-nums">{row.original.capacity}</span>,
  },
  {
    accessorKey: "building",
    header: "Building",
    cell: ({ row }) => row.original.building ?? "—",
  },
  {
    accessorKey: "amenities",
    header: "Amenities",
    cell: ({ row }) => {
      const parts = [row.original.has_projector && "Projector", row.original.has_ac && "AC"].filter(Boolean);
      return <span className="text-muted-foreground">{parts.join(" · ") || "—"}</span>;
    },
  },
];

export default function RoomsPage() {
  return (
    <ProtectedShell>
      <ResourcePage<Room>
        title="Rooms"
        endpoint="/api/v1/rooms"
        query={useRooms}
        columns={columns}
        fields={FIELDS}
        drilldown={{
          tile: { name: "room_type", label: "Room type", values: ROOM_TYPES, labels: { SEMINAR_HALL: "Seminar hall" } },
          rail: [
            { name: "building", label: "Building", values: ["Main", "Annex"] },
            { name: "min_capacity", label: "Capacity", values: ["40", "60", "80"], labels: { "40": "40+ seats", "60": "60+ seats", "80": "80+ seats" } },
          ],
        }}
        summary={(rows) => {
          const byType = new Map<string, number>();
          for (const r of rows) byType.set(r.room_type, (byType.get(r.room_type) ?? 0) + 1);
          const totalCap = rows.reduce((a, r) => a + r.capacity, 0);
          return [
            { label: "Rooms", value: rows.length },
            { label: "Seats", value: totalCap },
            ...Array.from(byType.entries()).map(([k, v]) => ({ label: k.replace("_", " "), value: v })),
          ];
        }}
        createPayload={() => ({
          name: "", room_code: "", room_type: "CLASSROOM", capacity: 40,
          building: "", floor: null, has_projector: false, has_ac: false,
        })}
        toPayload={(form) => ({
          name: String(form.name ?? ""),
          room_code: String(form.room_code ?? ""),
          room_type: String(form.room_type ?? "CLASSROOM"),
          capacity: Number(form.capacity ?? 0),
          building: form.building ? String(form.building) : null,
          floor: form.floor !== "" && form.floor !== null ? Number(form.floor) : null,
          has_projector: Boolean(form.has_projector),
          has_ac: Boolean(form.has_ac),
        })}
        toForm={(room) => ({
          name: room.name, room_code: room.room_code, room_type: room.room_type,
          capacity: room.capacity, building: room.building ?? "", floor: room.floor ?? "",
          has_projector: room.has_projector, has_ac: room.has_ac,
        })}
      />
    </ProtectedShell>
  );
}
