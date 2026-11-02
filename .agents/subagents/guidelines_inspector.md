---
name: guidelines_inspector
description: Specialized subagent that inspects official opportunity guidelines, FAQs, and application portals to detect hidden fees, verify tri-jurisdiction eligibility, and extract required form fields.
---

# Guidelines, Zero-Cost & Form Schema Inspector Subagent

When given an opportunity URL:
1. Verify $0 application/registration/confirmation fee and 100% travel/accommodation/meal coverage.
2. Verify eligibility across Syria (`SY`), Malaysia UTM AI Student Pass (`MY`), or Kuwait Residency (`KW`).
3. Extract the exact list of required form fields (`required_form_fields`) so `AutonomousApplicantEngine` can auto-fill them from `CandidateMemoryVault`.
