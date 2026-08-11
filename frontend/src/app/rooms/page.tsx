"use client";

import { ResourceTable, type FieldConfig } from "@/components/ResourceTable";
import { ProtectedShell } from "@/components/ProtectedShell";
import type { Room } from "@/lib/types";

const ROOM_TYPES = ["CLASSROOM", "LAB", "SEMINAR_HALL", "AUDITORIUM", "CUSTOM"];

function TypeBadge({ value }: { value: string }) {
  const styles: Record<string, string> = {
    CLASSROOM: "bg-sky-100 text-sky-800",
    LAB: "bg-violet-100 text-violet-800",
    SEMINAR_HALL: "bg-amber-100 text-amber-800",
    AUDITORIUM: "bg-emerald-100 text-emerald-800",
    CUSTOM: "bg-canvas-deep text-ink-soft",
  };
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[value] ?? "bg-canvas-deep text-ink-soft"}`}>
      {value.replace("_", " ")}
    </span>
  );
}

const FIELDS: FieldConfig[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "room_code", label: "Room code", type: "text", required: true },
  { name: "room_type", label: "Room type", type: "select", options: ROOM_TYPES, required: true },
  { name: "capacity", label: "Capacity", type: "number", required: true, min: 0 },
  { name: "building", label: "Building", type: "text" },
  { name: "floor", label: "Floor", type: "number", min: 0 },
  { name: "has_projector", label: "Projector", type: "checkbox" },
  { name: "has_ac", label: "Air conditioned", type: "checkbox" },
];

export default function RoomsPage() {
  return (
    <ProtectedShell>
      <ResourceTable<Room>
        title="Rooms"
        endpoint="/api/v1/rooms"
        columns={[
          { key: "name", label: "Name", render: (r) => <span className="font-medium text-ink">{r.name}</span> },
          { key: "room_code", label: "Code", render: (r) => <span className="text-ink-faint">{r.room_code}</span> },
          { key: "room_type", label: "Type", render: (r) => <TypeBadge value={r.room_type} /> },
          { key: "capacity", label: "Capacity", render: (r) => <span className="tabular-nums">{r.capacity}</span> },
          { key: "building", label: "Building", render: (r) => r.building ?? "—" },
          { key: "amenities", label: "Amenities", render: (r) => (
            <span className="text-ink-faint">
              {[r.has_projector && "Projector", r.has_ac && "AC"].filter(Boolean).join(" · ") || "—"}
            </span>
          ) },
        ]}
        fields={FIELDS}
        filters={[{ name: "room_type", label: "Room type", options: ROOM_TYPES }]}
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
          name: "",
          room_code: "",
          room_type: "CLASSROOM",
          capacity: 40,
          building: "",
          floor: null,
          has_projector: false,
          has_ac: false,
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
          name: room.name,
          room_code: room.room_code,
          room_type: room.room_type,
          capacity: room.capacity,
          building: room.building ?? "",
          floor: room.floor ?? "",
          has_projector: room.has_projector,
          has_ac: room.has_ac,
        })}
      />
    </ProtectedShell>
  );
}
