# Lead retention: what to hold, what to delete, and when

The app enforces this in **Leads -> Manage Lists -> Suggested cleanup**. Only leads nobody has
contacted are ever selected; DNC / opted-out leads and anything worked are never touched.

| Lead | Action | When |
|------|--------|------|
| Business personal property, minerals, utilities (not real estate) | Delete | Immediately |
| Duplicate property (same street + city) | Delete extras, keep best-scored copy with a source | Immediately |
| Pre-foreclosure, never contacted | Re-pull a fresh list, then delete the old rows | 60 days (Texas sales are the first Tuesday monthly) |
| COLD, never contacted | Delete | 90 days |
| WARM, never contacted | Delete | 180 days |
| Delinquent tax roll rows, never contacted | Replace with the new annual roll | 12 months |
| HOT / WARM not yet contacted | **Work them** | Call HOT within 48h, WARM within a week |
| Contacted / follow-up scheduled | Hold | 12 months from last contact, then archive |
| DNC / STOP / opted out | **Keep permanently** | Never delete: it is your suppression record (TCPA) |
| Appointments, offers, under contract, closed | Keep | 7 years |

Refresh cadence: re-pull pre-foreclosure lists monthly, probate quarterly, tax roll annually.
