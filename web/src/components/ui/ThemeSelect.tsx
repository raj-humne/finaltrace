import { useMemo } from "react";
import * as Select from "@radix-ui/react-select";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ThemeSelectOption {
  value: string;
  label: string;
  badgeDotColor?: string;
}

export interface ThemeSelectProps {
  value?: string;
  onValueChange: (val: string) => void;
  options: ThemeSelectOption[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  triggerClassName?: string;
}

const EMPTY_VALUE_SENTINEL = "__SENTINEL_ALL__";

export function ThemeSelect({
  value,
  onValueChange,
  options,
  placeholder,
  ariaLabel,
  className,
  triggerClassName,
}: ThemeSelectProps) {
  // Radix UI Select requires non-empty string values. Map empty string or undefined to sentinel.
  const mappedValue = value === "" || value === undefined ? EMPTY_VALUE_SENTINEL : value;

  const currentOption = useMemo(() => {
    return options.find((opt) => {
      const optVal = opt.value === "" ? EMPTY_VALUE_SENTINEL : opt.value;
      return optVal === mappedValue;
    });
  }, [options, mappedValue]);

  const handleValueChange = (newVal: string) => {
    onValueChange(newVal === EMPTY_VALUE_SENTINEL ? "" : newVal);
  };

  return (
    <Select.Root value={mappedValue} onValueChange={handleValueChange}>
      <Select.Trigger
        aria-label={ariaLabel}
        className={cn(
          "group inline-flex items-center justify-between gap-2.5 rounded-lg border border-white/15 bg-white/[0.06] backdrop-blur-md px-3.5 py-1.5 text-sm font-medium text-[#FBFBFB] outline-none transition-all duration-200 hover:border-white/30 hover:bg-white/[0.1] hover:shadow-[0_0_15px_rgba(255,255,255,0.06)] focus-visible:border-[#BCABAE] focus-visible:ring-1 focus-visible:ring-[#BCABAE]/50 data-[state=open]:border-[#BCABAE] data-[state=open]:bg-white/[0.1]",
          className,
          triggerClassName
        )}
      >
        <span className="flex items-center gap-2 truncate">
          {currentOption?.badgeDotColor && (
            <span
              className="inline-block h-2 w-2 rounded-full shrink-0 shadow-sm"
              style={{
                backgroundColor: currentOption.badgeDotColor,
                boxShadow: `0 0 8px ${currentOption.badgeDotColor}80`,
              }}
            />
          )}
          <Select.Value placeholder={placeholder}>
            {currentOption?.label ?? placeholder}
          </Select.Value>
        </span>
        <Select.Icon asChild>
          <ChevronDown className="h-4 w-4 text-[#BCABAE] transition-transform duration-250 ease-out group-data-[state=open]:rotate-180 shrink-0" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          align="start"
          className="theme-select-content z-50 min-w-[9rem] max-h-80 overflow-y-auto rounded-xl border border-white/15 bg-[#141518]/95 p-1.5 backdrop-blur-xl shadow-[0_16px_40px_rgba(0,0,0,0.65),inset_0_1px_1px_rgba(255,255,255,0.12)]"
        >
          <Select.Viewport className="p-0.5">
            {options.map((opt) => {
              const optVal = opt.value === "" ? EMPTY_VALUE_SENTINEL : opt.value;
              return (
                <Select.Item
                  key={optVal}
                  value={optVal}
                  className="theme-select-item"
                >
                  {opt.badgeDotColor && (
                    <span
                      className="inline-block h-2 w-2 rounded-full shrink-0"
                      style={{
                        backgroundColor: opt.badgeDotColor,
                        boxShadow: `0 0 6px ${opt.badgeDotColor}80`,
                      }}
                    />
                  )}
                  <Select.ItemText>{opt.label}</Select.ItemText>
                  <Select.ItemIndicator className="ml-auto flex items-center justify-center pl-2">
                    <Check className="h-3.5 w-3.5 text-[#BCABAE]" />
                  </Select.ItemIndicator>
                </Select.Item>
              );
            })}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
