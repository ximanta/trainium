/** Persona type ids as a person reads them: "senior_practitioner" becomes
 *  "Senior Practitioner". Shared so the admin console and the green room label
 *  the same learner the same way.
 */
export function formatPersonaType(type: string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
