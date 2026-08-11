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
  triggered_at: string;
  completed_at: string | null;
  error_log: string | null;
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
