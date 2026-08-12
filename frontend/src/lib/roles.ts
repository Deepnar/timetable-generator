export type Role = "admin" | "hod" | "teacher" | "student";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  hod: "Dept. Head",
  teacher: "Teacher",
  student: "Student",
};

export interface NavItem {
  label: string;
  path: string;
  roles: Role[];
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    group: "Overview",
    items: [{ label: "Dashboard", path: "/dashboard", roles: ["admin", "hod"] }],
  },
  {
    group: "Scheduling",
    items: [
      { label: "Generation", path: "/generate", roles: ["admin", "hod"] },
      { label: "Instances", path: "/instances", roles: ["admin", "hod"] },
      { label: "Assignments", path: "/assignments", roles: ["admin", "hod"] },
    ],
  },
  {
    group: "Resources",
    items: [
      { label: "Rooms", path: "/rooms", roles: ["admin", "hod"] },
      { label: "Faculty", path: "/faculty", roles: ["admin", "hod"] },
      { label: "Groups", path: "/groups", roles: ["admin", "hod"] },
      { label: "Subjects", path: "/subjects", roles: ["admin", "hod"] },
    ],
  },
  {
    group: "Configuration",
    items: [
      { label: "Profiles", path: "/profiles", roles: ["admin", "hod"] },
      { label: "Constraints", path: "/constraints", roles: ["admin"] },
      { label: "Settings", path: "/settings", roles: ["admin"] },
      { label: "Users", path: "/users", roles: ["admin"] },
    ],
  },
  {
    group: "Output",
    items: [
      { label: "Exports", path: "/exports", roles: ["admin", "hod", "teacher", "student"] },
      { label: "Notifications", path: "/notifications", roles: ["admin", "hod", "teacher", "student"] },
    ],
  },
  {
    group: "My space",
    items: [
      { label: "My Schedule", path: "/my-schedule", roles: ["teacher"] },
      { label: "My Timetable", path: "/my-timetable", roles: ["student"] },
    ],
  },
];

export function navFor(role: string): NavGroup[] {
  return NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.roles.includes(role as Role)),
  })).filter((g) => g.items.length > 0);
}
