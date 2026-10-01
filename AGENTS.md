# Community workspace agent guide

This repository contains reusable Bifrost modules, workflows, agents, and apps for MSPs. It is a reference and porting starting point, not a ready-to-run customer deployment. Read [README.md](README.md), [CLAUDE.md](CLAUDE.md), and the relevant component before copying or changing behavior. CLAUDE.md owns the existing Halo list-payload/DotDict/SQL conventions and SDK table, form, AI, and CLI constraints; preserve them when porting.

## Code map

`modules/` holds vendor integrations; `modules/extensions/` adds pagination, enriched operations, permissions, and remote execution helpers. Apps and workflows consume those modules; feature-specific workflows live in `features/`. Treat the large auto-generated Halo SDK as generated code; change its generation path rather than hand-editing it. Preserve each vendor's authentication, pagination, region selection, and API error handling when adapting a component. Use public Bifrost documentation linked from the README for platform concepts.

## Porting and operational boundaries

Generalize contributions: no organization IDs, customer records, credentials, tenant URLs, or live query results. Configuration names belong in examples; values resolve in the destination workspace. Review target authorization and integration configuration instead of assuming the reference's settings are correct for another tenant.

Ticket updates, Graph email, CSP/GDAP consent, remote PowerShell, and AutoElevate approvals can change external systems. Source editing or porting does not authorize those operations. Preserve RBAC checks and approval-policy boundaries; inspect read-only evidence first and use synthetic fixtures wherever possible.

## Verification

Follow any component-specific manifest or workflow discovered in the tree. No root test runner or CI workflow was found in the inspected default branch. State which checks were actually run and identify untested vendor behavior. Validate portable imports and the destination SDK contract before deployment; distinguish a source contribution from successful registry synchronization and live execution proof.
