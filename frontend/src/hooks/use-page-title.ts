import { useEffect } from "react";

const BRAND = "Continuum";

/**
 * Sets the document title on every route.
 * Call at the top of each page component:
 *   usePageTitle("Dashboard") → "Continuum | Dashboard"
 *   usePageTitle()            → "Continuum | Project Continuity"
 */
export function usePageTitle(section?: string): void {
  useEffect(() => {
    document.title = section ? `${BRAND} | ${section}` : `${BRAND} | Project Continuity`;
    return () => {
      // Reset to the brand name when the component unmounts (navigation in progress)
      document.title = BRAND;
    };
  }, [section]);
}
