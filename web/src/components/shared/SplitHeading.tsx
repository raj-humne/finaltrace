import { useEffect, useRef } from "react";
import gsap from "gsap";

interface SplitHeadingProps {
  text: string;
  className?: string;
  as?: "h1" | "h2" | "h3";
}

/**
 * Systematic, professional character-by-character cascade entrance animation using GSAP.
 * Each character rises from down to up with staggered timing through an overflow mask.
 */
export function SplitHeading({
  text,
  className = "",
  as: Component = "h1",
}: SplitHeadingProps) {
  const containerRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chars = containerRef.current.querySelectorAll(".split-char");
    if (!chars.length) return;

    // Reset initial state then animate from down to up
    gsap.fromTo(
      chars,
      {
        y: "120%",
        opacity: 0,
      },
      {
        y: "0%",
        opacity: 1,
        duration: 0.7,
        stagger: 0.032,
        ease: "power3.out",
        overwrite: "auto",
      }
    );
  }, [text]);

  const words = text.split(" ");

  return (
    <Component
      ref={containerRef}
      className={`font-akira text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-wider text-[#FBFBFB] ${className}`}
      aria-label={text}
    >
      {words.map((word, wIdx) => (
        <span key={wIdx} className="inline-block whitespace-nowrap overflow-hidden pb-1">
          {word.split("").map((char, cIdx) => (
            <span
              key={cIdx}
              className="split-char inline-block will-change-transform"
            >
              {char}
            </span>
          ))}
          {wIdx < words.length - 1 && <span className="inline-block">&nbsp;</span>}
        </span>
      ))}
    </Component>
  );
}
