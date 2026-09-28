import { useEffect } from "react";
import gsap from "gsap";

/**
 * Universal 3D Tilt Engine for Inner Cards.
 * 
 * Rules:
 * 1. The main big container (.glass-container) does NOT tilt at all.
 * 2. All inner cards (.glass-card, .tilt-card, [data-tilt]) tilt interactively
 *    with a silky-smooth, subtle 3D response.
 * 3. High performance via RAF and clamped coordinates to prevent any edge jitter.
 */
export function useGsap3DTilt() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    let activeCard: HTMLElement | null = null;
    let rafId: number | null = null;

    // 1. Subtle screen-wide parallax for Akira headings and subheadings
    function onMouseMoveScreen(e: MouseEvent) {
      const normX = e.clientX / window.innerWidth - 0.5;
      const normY = e.clientY / window.innerHeight - 0.5;

      gsap.to(".font-akira, h1", {
        rotateY: normX * 4,
        rotateX: -normY * 4,
        x: normX * 6,
        y: normY * 4,
        transformPerspective: 1200,
        ease: "power1.out",
        duration: 0.6,
        overwrite: "auto",
      });

      gsap.to("h2, h3, .tilt-subheading", {
        rotateY: normX * 2.5,
        rotateX: -normY * 2.5,
        x: normX * 4,
        y: normY * 3,
        transformPerspective: 1200,
        ease: "power1.out",
        duration: 0.7,
        overwrite: "auto",
      });
    }

    // 2. Smooth 3D tilt specifically on INNER CARDS (.glass-card, .tilt-card, [data-tilt])
    function onPointerMove(e: PointerEvent) {
      // Find the closest inner card - explicitly excluding .glass-container
      const target = (e.target as HTMLElement)?.closest<HTMLElement>(
        ".glass-card, .tilt-card, [data-tilt]"
      );

      if (target) {
        if (activeCard !== target) {
          if (activeCard) resetCard(activeCard);
          activeCard = target;
        }

        const rect = target.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        // Clamp coordinates to [-0.5, 0.5] for smooth boundary containment
        const rawX = (e.clientX - rect.left) / rect.width - 0.5;
        const rawY = (e.clientY - rect.top) / rect.height - 0.5;
        const x = Math.max(-0.5, Math.min(0.5, rawX));
        const y = Math.max(-0.5, Math.min(0.5, rawY));

        // Smooth minimal tilt (3.5 degrees max)
        const maxTilt = 3.5;
        const tiltX = -y * maxTilt;
        const tiltY = x * maxTilt;

        if (rafId) cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => {
          gsap.to(target, {
            rotateX: tiltX,
            rotateY: tiltY,
            transformPerspective: 1000,
            transformOrigin: "center center",
            duration: 0.35,
            ease: "power2.out",
            overwrite: "auto",
          });
        });
      } else if (activeCard) {
        resetCard(activeCard);
        activeCard = null;
      }
    }

    function resetCard(card: HTMLElement) {
      gsap.to(card, {
        rotateX: 0,
        rotateY: 0,
        duration: 0.55,
        ease: "power2.out",
        overwrite: "auto",
      });
    }

    function onPointerLeave(e: PointerEvent) {
      if (activeCard && (!e.relatedTarget || !activeCard.contains(e.relatedTarget as Node))) {
        resetCard(activeCard);
        activeCard = null;
      }
    }

    window.addEventListener("mousemove", onMouseMoveScreen, { passive: true });
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    document.addEventListener("pointerleave", onPointerLeave, { passive: true });

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener("mousemove", onMouseMoveScreen);
      window.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerleave", onPointerLeave);
      if (activeCard) {
        resetCard(activeCard);
      }
    };
  }, []);
}
