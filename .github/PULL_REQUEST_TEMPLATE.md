## Summary
- Explain the change in 1-3 bullets.

## Validation
- [ ] `pnpm --filter web lint`
- [ ] `pnpm --filter web typecheck`
- [ ] `pnpm --filter web test`
- [ ] `pytest apps/api/tests`
- [ ] `pytest services/worker/tests`
- [ ] Documentation updated where needed

## Risk Review
- [ ] No secrets or connection strings were committed
- [ ] No tenant-isolation behavior was weakened
- [ ] No publish-gate or verifier policy was bypassed

## Screenshots / Notes
- Add UI evidence or implementation notes if relevant.
