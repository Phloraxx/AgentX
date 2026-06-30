/** useStickToBottom — keep a scroll container pinned to the newest content,
 *  but only while the user hasn't scrolled up to read history. */

import { useEffect, useRef } from "react";

const NEAR_BOTTOM_PX = 48;

export function useStickToBottom<T extends HTMLElement>(dep: number) {
  const ref = useRef<T | null>(null);
  const stuck = useRef(true);

  // Track whether the user is parked near the bottom before each content change.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      stuck.current =
        el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el || !stuck.current) return;
    el.scrollTop = el.scrollHeight;
  }, [dep]);

  return ref;
}
