# Hot context

- Slices 1-5 are implemented and verified offline: fixture read path, catalog policy and both
  selection paths, reports, governed fake writes, MDA/self-hosted/Slack/API surfaces.
- Live provider mutations are not released. `WriteGate` refuses live providers and no runtime
  profile constructs one. Slice 6 needs explicit human authorization.
- Live Pipeboard reads are implemented but unverified against a real token in this session; run the
  opt-in integration test before claiming live read support.
- PDF rendering depends on WeasyPrint native libraries; HTML is the fallback artifact.
- Keep the public wiki generic. Source current capabilities from live schemas, not copied counts.
