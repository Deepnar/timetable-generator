"use client";

import { ResourceTable, type FieldConfig } from "@/components/ResourceTable";
import { ProtectedShell } from "@/components/ProtectedShell";
import type { Room } from "@/lib/types";

const ROOM_TYPES = ["CLASSROOM", "LAB", "SEMINAR_HALL", "AUDITORIUM", "CUSTOM"];

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
          { key: "name", label: "Name", render: (r) => <span className="font-medium">{r.name}</span> },
          { key: "room_code", label: "Code" },
          { key: "room_type", label: "Type" },
          { key: "capacity", label: "Capacity" },
          { key: "building", label: "Building", render: (r) => r.building ?? "—" },
          { key: "has_projector", label: "Projector", render: (r) => (r.has_projector ? "Yes" : "No") },
          { key: "has_ac", label: "AC", render: (r) => (r.has_ac ? "Yes" : "No") },
        ]}
        fields={FIELDS}
        filters={[{ name: "room_type", label: "Room type", options: ROOM_TYPES }]}
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
