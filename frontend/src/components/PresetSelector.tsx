import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { PresetInfo } from '@/types/upcoming';

interface PresetSelectorProps {
  value: string;
  onChange: (presetName: string) => void;
  presets: PresetInfo[];
}

export default function PresetSelector({ value, onChange, presets }: PresetSelectorProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger style={{ maxWidth: '220px' }}>
        <SelectValue placeholder="Select preset..." />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="custom">Custom</SelectItem>
        {presets.map((preset) => (
          <SelectItem key={preset.name} value={preset.name}>
            {preset.display_name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
