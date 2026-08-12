/** Response shapes mirroring the backend Pydantic schemas. */

export interface Room {
  id: number;
  name: string;
  room_code: string;
  room_type: string;
  capacity: number;
  building: string | null;
  floor: number | null;
  has_projector: boolean;
  has_ac: boolean;
  equipment_json: string[] | null;
  is_active: boolean;
}

export interface Faculty {
  id: number;
  name: string;
  email: string;
  department: string;
  max_hours_per_week: number;
  max_hours_per_day: number;
  is_active: boolean;
}

export interface StudentGroup {
  id: number;
  name: string;
  group_type: string;
  department: string;
  year: number | null;
  semester: number | null;
  strength: number;
  is_active: boolean;
  incharge_email: string | null;
}

export interface Subject {
  id: number;
  name: string;
  subject_code: string;
  department: string;
  semester: number;
  hours_per_week: number;
  requires_lab: boolean;
  requirements_json: Record<string, unknown> | null;
  is_active: boolean;
}

export interface Generation {
  id: number;
  profile_id: number | null;
  combination_id: number | null;
  academic_year: string;
  semester: number | null;
  timetable_type: string;
  generation_status: string;
  algorithm_used: string;
  variation: string;
  instances_requested: number;
  instances_produced: number;
  score_best_instance: number | null;
  run_duration_ms: number | null;
  triggered_at: string;
  completed_at: string | null;
  error_log: string | null;
  placement_warning: string | null;
}

export interface Instance {
  id: number;
  generation_id: number;
  instance_number: number;
  label: string | null;
  soft_score: number | null;
  hard_violations: number;
  status: string;
  selected_at: string | null;
  published_at: string | null;
  notes: string | null;
}

export interface Slot {
  id: number;
  instance_id: number;
  slot_date: string | null;
  day_of_week: number | null;
  slot_number: number;
  start_time: string;
  end_time: string;
  subject_id: number | null;
  faculty_id: number | null;
  room_id: number | null;
  student_group_id: number | null;
  session_type: string;
  is_manual_override: boolean;
  override_reason: string | null;
  external_speaker: string | null;
  notes: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface Me {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface Profile {
  id: number;
  name: string;
  description: string | null;
  scope_type: string;
  academic_year: string;
  semester: number | null;
  department: string | null;
  is_active: boolean;
  is_archived: boolean;
  created_at: string;
}

export interface SubjectAssignment {
  id: number;
  subject_id: number;
  faculty_id: number | null;
  group_id: number;
  weekly_hours: number;
  load_share: number;
}

export interface ProfileResource {
  id: number;
  profile_id: number;
  resource_type: string;
  resource_id: number;
}

export interface ProfileParameter {
  id: number;
  profile_id: number;
  param_key: string;
  param_value: string;
  param_type: string;
  description: string | null;
}

export interface HardConstraint {
  id: number;
  profile_id: number | null;
  constraint_type: string;
  config_json: Record<string, unknown> | null;
  description: string | null;
  is_active: boolean;
}

export interface SoftConstraint {
  id: number;
  profile_id: number | null;
  constraint_type: string;
  config_json: Record<string, unknown> | null;
  weight: number;
  description: string | null;
  is_active: boolean;
}

export interface ConstraintTypes {
  hard: string[];
  soft: string[];
}

export interface OverrideDetail {
  id: number;
  instance_id: number;
  slot_id: number | null;
  override_type: string;
  new_faculty_id: number | null;
  new_room_id: number | null;
  swap_with_slot_id: number | null;
  date_from: string | null;
  date_to: string | null;
  reason: string | null;
  created_by: number | null;
  resolved_at: string | null;
  created_at: string;
  slot_day: number | null;
  slot_number: number | null;
  subject_code: string | null;
  subject_name: string | null;
  group_name: string | null;
  old_faculty_name: string | null;
  new_faculty_name: string | null;
  old_room_code: string | null;
  new_room_code: string | null;
}

export interface AvailableFaculty {
  id: number;
  name: string;
  email: string | null;
  department: string;
}

export interface MyFaculty {
  id: number;
  name: string;
  email: string;
  department: string;
}

export interface MyGroup {
  id: number;
  name: string;
  department: string;
  year: number | null;
  semester: number | null;
}

export interface MySlot {
  id: number;
  day_of_week: number | null;
  slot_number: number;
  start_time: string;
  end_time: string;
  subject_code: string | null;
  subject_name: string | null;
  room_code: string | null;
  group_name: string | null;
  faculty_name: string | null;
  session_type: string;
  is_manual_override: boolean;
}

export interface MyScheduleResponse {
  faculty: MyFaculty | null;
  slots: MySlot[];
  published_instance_ids: number[];
}

export interface MyTimetableResponse {
  group: MyGroup | null;
  slots: MySlot[];
  published_instance_ids: number[];
}

export interface MyTodayResponse {
  faculty: MyFaculty | null;
  group: MyGroup | null;
  day_of_week: number;
  slots: MySlot[];
}
