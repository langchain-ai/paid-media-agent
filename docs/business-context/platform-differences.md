# Platform differences

The normalized model supports comparison without erasing each platform's operating model.

| Platform family | Typical role | Important differences to preserve |
|---|---|---|
| Search ads | capture expressed demand | query intent, match type, negatives, search terms, quality and rank, budget and bid strategy |
| Social feed ads | create or harvest demand | audience construction, placement, creative format, frequency, optimization event, view-through credit |
| Professional network ads | B2B reach and lead capture | company/job targeting, lead forms, longer sales cycles, smaller high-value samples |
| Community ads | contextual and interest reach | community targeting, promoted-post lifecycle, conversation fit, smaller audience pools |
| Video and display | awareness, education, retargeting | viewability, completed views, reach, frequency, assisted outcomes, creative sequencing |
| Chat-surface ads (OpenAI Ads) | intent capture inside assistant conversations | new placement semantics, sparse benchmarks, reported conversions only |

Source paths differ: Google, Meta, and Reddit arrive through Pipeboard MCP; LinkedIn, X, and OpenAI
Ads arrive through direct adapters. LinkedIn reports `externalWebsiteConversions` (click and view
attributed), X reports `conversion_purchases` from its web conversion metric group, and OpenAI Ads
reports its own `conversions`. None of these are comparable to each other or to Pipeboard platforms
without an explicit attribution note.

Entity names and lifecycle states vary. Normalize into common concepts only when semantics match. Keep
provider-native fields under `source_fields` for analysis that needs them.

New campaign creation defaults to non-serving state where supported. Drafting creative, creating a
campaign shell, and activating delivery are distinct actions and approvals.

The source of current platform capability is the live Pipeboard schema and provider documentation in
[sources.md](sources.md), not this table.

