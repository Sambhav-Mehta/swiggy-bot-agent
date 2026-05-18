/** Convert the persona form object into the API Persona shape. */
export function buildPersonaPayload(form) {
  return {
    name:        form.name.trim(),
    location:    form.location.trim(),
    diet_goals:  form.diet_goals.trim(),
    restrictions: form.restrictions.trim(),
    preferences: form.preferences.trim(),
    budget_wkday: form.budget_wkday.trim(),
    budget_wknd:  form.budget_wknd.trim(),
    address_id:   form.address_id?.trim() || '',
  }
}

export const EMPTY_PERSONA = {
  name: '', location: '', diet_goals: '', restrictions: '',
  preferences: '', budget_wkday: '', budget_wknd: '', address_id: '',
}
