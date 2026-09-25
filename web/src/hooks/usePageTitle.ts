import { useEffect } from "react";

/** So an analyst juggling multiple tabs can tell them apart at a glance. */
export function usePageTitle(title: string | undefined) {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} - SentinelTrace` : "SentinelTrace";
    return () => {
      document.title = previous;
    };
  }, [title]);
}
