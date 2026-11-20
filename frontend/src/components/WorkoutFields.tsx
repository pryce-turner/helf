import { Hash, Minus, Plus, Weight, Timer } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Exercise } from "@/types/exercise";

/**
 * The field groups a set tile can carry, driven by the exercise's field
 * configuration (plan 0018). Shared by the day view's add form and the
 * per-tile inline editor so "what a tile offers" has exactly one answer.
 *
 * A group renders when the exercise has it enabled **or the tile already
 * carries a value for it**: changing an exercise never rewrites history, so
 * an existing value stays visible (and editable) even after its group is
 * disabled. With no exercise selected yet — the blank add form — Reps and
 * Weight render, matching what the form has always offered.
 */

export interface WorkoutFieldValues {
  weight?: number | null;
  weight_unit?: string;
  reps?: number | null;
  distance?: number | null;
  distance_unit?: string | null;
  work_seconds?: number | null;
  rest_seconds?: number | null;
  rest_after_seconds?: number | null;
}

interface WorkoutFieldsProps {
  /** The exercise whose configuration drives the inputs; undefined = none picked yet. */
  exercise?: Exercise;
  values: WorkoutFieldValues;
  onChange: (patch: Partial<WorkoutFieldValues>) => void;
  /** Keeps label/input ids unique between the add form and tile editors. */
  idPrefix: string;
}

// Weight increment based on current weight value
const getWeightIncrement = (weight: number): number => {
  if (weight < 100) return 2.5;
  if (weight <= 300) return 5;
  return 10;
};

const parseNumber = (raw: string): number | null =>
  raw ? parseFloat(raw) : null;

const parseInteger = (raw: string): number | null =>
  raw ? parseInt(raw, 10) : null;

const WorkoutFields = ({
  exercise,
  values,
  onChange,
  idPrefix,
}: WorkoutFieldsProps) => {
  const showReps = !exercise || exercise.reps_enabled || values.reps != null;
  const showWeight =
    !exercise || exercise.weight_enabled || values.weight != null;
  const showDistance =
    exercise?.distance_enabled ||
    values.distance != null ||
    values.distance_unit != null;
  const showTime =
    exercise?.time_enabled ||
    values.work_seconds != null ||
    values.rest_seconds != null ||
    values.rest_after_seconds != null;

  return (
    <>
      <div
        className="grid grid-cols-1 md:grid-cols-2"
        style={{ gap: "var(--space-4)" }}
      >
        {showWeight && (
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-weight`} className="form-label">
              <Weight style={{ width: "14px", height: "14px" }} />
              Weight
            </Label>
            <div className="stepper">
              <button
                type="button"
                className="stepper__btn stepper__btn--start"
                aria-label="Decrease weight"
                onClick={() => {
                  const current = values.weight || 0;
                  const increment = getWeightIncrement(current);
                  onChange({ weight: Math.max(0, current - increment) });
                }}
              >
                <Minus style={{ width: "18px", height: "18px" }} />
              </button>
              <input
                id={`${idPrefix}-weight`}
                type="number"
                inputMode="decimal"
                step="0.1"
                placeholder="0"
                className="input--stepper"
                value={values.weight ?? ""}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  onChange({ weight: parseNumber(e.target.value) })
                }
              />
              <button
                type="button"
                className="stepper__btn stepper__btn--end"
                aria-label="Increase weight"
                onClick={() => {
                  const current = values.weight || 0;
                  const increment = getWeightIncrement(current);
                  onChange({ weight: current + increment });
                }}
              >
                <Plus style={{ width: "18px", height: "18px" }} />
              </button>
              <span className="stepper__unit">
                {values.weight_unit || "lbs"}
              </span>
            </div>
          </div>
        )}

        {showReps && (
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-reps`} className="form-label">
              <Hash style={{ width: "14px", height: "14px" }} />
              Reps
            </Label>
            <div className="stepper">
              <button
                type="button"
                className="stepper__btn stepper__btn--start"
                aria-label="Decrease reps"
                onClick={() => {
                  const current = values.reps || 0;
                  const next = Math.max(0, current - 1);
                  onChange({ reps: next > 0 ? next : null });
                }}
              >
                <Minus style={{ width: "18px", height: "18px" }} />
              </button>
              <input
                id={`${idPrefix}-reps`}
                type="number"
                inputMode="numeric"
                placeholder="e.g., 5"
                className="input--stepper input--mono"
                value={values.reps ?? ""}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  onChange({ reps: parseInteger(e.target.value) })
                }
              />
              <button
                type="button"
                className="stepper__btn stepper__btn--end"
                aria-label="Increase reps"
                onClick={() => onChange({ reps: (values.reps || 0) + 1 })}
              >
                <Plus style={{ width: "18px", height: "18px" }} />
              </button>
            </div>
          </div>
        )}
      </div>

      {showDistance && (
        <div
          className="grid grid-cols-1 md:grid-cols-2"
          style={{ gap: "var(--space-4)" }}
        >
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-distance`} className="form-label">
              Distance
            </Label>
            <Input
              id={`${idPrefix}-distance`}
              type="number"
              inputMode="decimal"
              placeholder="e.g., 40"
              value={values.distance ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                onChange({ distance: parseNumber(e.target.value) })
              }
            />
          </div>
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-distance-unit`} className="form-label">
              Distance unit
            </Label>
            <select
              id={`${idPrefix}-distance-unit`}
              className="input"
              value={values.distance_unit ?? ""}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                onChange({ distance_unit: e.target.value || null })
              }
            >
              <option value="">unit</option>
              <option value="m">m</option>
              <option value="km">km</option>
              <option value="mi">mi</option>
              <option value="yd">yd</option>
            </select>
          </div>
        </div>
      )}

      {showTime && (
        <div
          className="grid grid-cols-3"
          style={{ gap: "var(--space-3)" }}
        >
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-work`} className="form-label">
              <Timer style={{ width: "14px", height: "14px" }} />
              Work seconds
            </Label>
            <Input
              id={`${idPrefix}-work`}
              type="number"
              inputMode="numeric"
              className="input--mono"
              placeholder="—"
              min={1}
              max={3600}
              value={values.work_seconds ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                onChange({ work_seconds: parseInteger(e.target.value) })
              }
            />
          </div>
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-rest`} className="form-label">
              Rest seconds
            </Label>
            <Input
              id={`${idPrefix}-rest`}
              type="number"
              inputMode="numeric"
              className="input--mono"
              placeholder="—"
              min={0}
              max={3600}
              value={values.rest_seconds ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                onChange({ rest_seconds: parseInteger(e.target.value) })
              }
            />
          </div>
          <div className="form-field">
            <Label htmlFor={`${idPrefix}-rest-after`} className="form-label">
              Rest after set seconds
            </Label>
            <Input
              id={`${idPrefix}-rest-after`}
              type="number"
              inputMode="numeric"
              className="input--mono"
              placeholder="—"
              min={0}
              max={3600}
              value={values.rest_after_seconds ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                onChange({
                  rest_after_seconds: parseInteger(e.target.value),
                })
              }
            />
          </div>
        </div>
      )}
    </>
  );
};

export default WorkoutFields;
