# Interaction & Forms
- Buttons: 3 weights; max 1 primary/screen, only if one action dominates; equal actions -> same secondary; minor/destructive -> tertiary; text-like tertiary gets underline/icon; fill-less needs 3:1 border; no gray/pale enabled fills; type="button" unless submitting.
- Targets: primary/frequent ones larger, near focus; 8px+ gaps; enlarge for motion, kids, elders; dots/swatches get full hit area.
- Labels: visible for/id label, never placeholder; unique descriptive control text; icons get text.
- Forms: cut derivable fields; max 2 optional, marked; 2-3 options -> radios; order standard else by frequency; width = expected length; autocomplete personal data; fieldset+legend; conditional fields only when relevant; state format rules upfront; accept common formats; no Reset; Cancel weaker than Submit.
- Errors: none on blur of empty fields; IF error-prone -> live hints; on fail -> linked summary above form + field message via aria-describedby, 3+ cues; keep input; copy = specific problem + fix, no blame/codes/humor; offer inferred fixes; modal only if blocking; info -> toast.
- Feedback: respond <400ms, else skeleton/progress bar; scale to impact; confirm completion.
- Safety: confirm consequential actions; undo; Cancel exit everywhere; extendable timeouts; announce new-tab links.
- Flow: split complex tasks into steps; highlight recommended option; reveal controls when relevant; tab order = visual; consistent terms.
- Nav: 5 or fewer -> labeled bar; more -> labeled Menu + cross-links; task-centric -> hub home; no carousel nav.
