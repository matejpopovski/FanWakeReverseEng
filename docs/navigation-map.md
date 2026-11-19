# Navigation map (FanWake, observed)

All authenticated routes take `?model=<creator uuid>`; the app is a Next.js App Router site (RSC fetches `?_rsc=`).

```
Sidebar
├── @handle · Connected   (model switcher, dropdown chevron)
├── Overview      /overview
├── Fans          /fans          → right-side drawer per fan: Overview | Content | Engine | Activity
├── Review        /review
├── Autopilot     /autopilot     (single long form, sticky Save)
├── PPV           /ppv           (inline "New template" form, Edit/Pause per card)
├── Re-engage     /re-engage     (single long form, Save)
├── Persona       /character     (single long form, Save)
├── Connect       /connect
├── Account       /account       (/settings redirects here)
├── Billing       /billing
├── Upgrade to Elite → /billing
├── Refer & Earn     → /billing
└── Sign out
Floating: "N replying" live pill (bottom-left), vendor support chat (bottom-right)
```

Cross-links observed: KPI cards → /fans or /review; "Manage →" on PPV card → /autopilot; top-fan rows → /fans;
Quick actions → /review, /character, /settings(/account), /fans; banners on /review and /autopilot → /character.

Collapsible sections ("▶ View rules / View triggers / View conditions / Advanced") are client-side toggles.
