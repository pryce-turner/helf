import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { PresetInfo } from '@/types/upcoming';

interface PresetSelectorProps {
  /** "custom", a built-in program's key, or "mine:<id>" for one of yours. */
  value: string;
  onChange: (value: string) => void;
  presets: PresetInfo[];
  /** Your saved programs (plan 0022), listed under the built-in ones. */
  programs?: { doc_id: number; name: string }[];
}

export default function PresetSelector({ value, onChange, presets, programs = [] }: PresetSelectorProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger style={{ maxWidth: '260px' }} aria-label="Program">
        <SelectValue placeholder="Select program" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="custom">Custom</SelectItem>
        {programs.length > 0 && (
          <SelectGroup>
            <SelectLabel>Yours</SelectLabel>
            {programs.map((program) => (
              <SelectItem key={program.doc_id} value={`mine:${program.doc_id}`}>
                {program.name}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        <SelectGroup>
          <SelectLabel>Built-in</SelectLabel>
          {presets.map((preset) => (
            <SelectItem key={preset.name} value={preset.name}>
              {preset.display_name}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
