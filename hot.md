# Hot context

- Slices 1-7 are implemented and verified offline. The repository is pushed to a private GitHub
  remote; the public release still needs the gates in `open-questions.md` (license approval,
  maintainer security contact, live read verification).
- Slice 6 readiness is implemented: the live write adapter exists but `WriteGate` refuses it
  until the operator clears every gate in `docs/operations/live-write-runbook.md`. No live canary
  has run; that still needs separate human authorization.
- Live Pipeboard reads are implemented but unverified against a real token in this session; run the
  opt-in integration test before claiming live read support.
- PDF rendering depends on WeasyPrint native libraries; HTML is the fallback artifact.
- Keep the public wiki generic. Source current capabilities from live schemas, not copied counts.
