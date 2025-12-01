import { useEffect, useRef } from 'react';

/**
 * A custom hook that sets up an IntersectionObserver to trigger a callback
 * when the user scrolls near the bottom of a list.
 * * @param callback The function to call to load more data.
 * @param isFetching Boolean indicating if data is currently being fetched.
 * @param hasMore Boolean indicating if there are more items to load.
 * @returns A ref to be attached to the sentinel/trigger element at the bottom of the list.
 */
export const useInfiniteScroll = (
  callback: () => void,
  isFetching: boolean,
  hasMore: boolean
) => {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const triggerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const trigger = triggerRef.current;
    
    // If the trigger element isn't mounted, or we are already fetching, or there is no more data, do nothing.
    if (!trigger || isFetching || !hasMore) return;

    // Disconnect existing observer if it exists to avoid duplicates
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    const observer = new IntersectionObserver((entries) => {
      // If the sentinel element comes into view (or within the rootMargin buffer)
      if (entries[0].isIntersecting) {
        callback();
      }
    }, {
      root: null, // Use the viewport as the container
      rootMargin: '200px', // Trigger the callback 200px before reaching the actual element
      threshold: 0.1 // Trigger when even a tiny part of the sentinel is visible
    });

    observer.observe(trigger);
    observerRef.current = observer;

    // Cleanup function
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [callback, isFetching, hasMore]);

  return triggerRef;
};