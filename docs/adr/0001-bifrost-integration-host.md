# Architecture Decision Records

## ADR-001: BiFrost as Primary Integration Host

**Date**: 2026-04-06  
**Status**: Accepted

### Context
Midtown needs to replace core ImmyBot workflows (software deployment, new device onboarding, desired-state enforcement) and unify integration architecture. Multiple orchestration contenders were evaluated: HaloPSA, Bifrost Integrations, and n8n.

### Decision
Implement all new integration work as **BiFrost-hosted application modules**:
- NinjaOne deployment/onboarding module
- Customer Offboarding meta-workflow
- Google Workspace GAM module

### Consequences
- HaloPSA remains for ticketing/agreements; Bifrost owns cross-platform orchestration
- n8n available for visual/low-code workflows but not default
- Platform adapters in `code/PlatformAdapters/` become legacy (testing artifacts)
- Future adapters built as BiFrost service-layer clients

---

## ADR-002: Customer Offboarding as Meta-Workflow

**Date**: 2026-04-06  
**Status**: Accepted

### Context
Wyndham offboarding required manual cleanup across 7+ platforms. Discrete issues (#51-58, #80) tracked one-time tasks. This pattern doesn't scale.

### Decision
**Reframe customer offboarding as a repeatable BiFrost meta-workflow.** Wyndham issues become requirements for the reference implementation.

### Workflow Stages
1. Trigger (HaloPSA ticket / scheduled / API)
2. Discover assets across all platforms
3. Confirm scope with technician
4. Queue platform-specific removal jobs
5. Execute removals via BiFrost workers
6. Verify & capture evidence
7. Close & notify stakeholders

### Consequences
- Future offboardings: "Run BiFrost offboarding workflow" not ad-hoc tickets
- Platform handlers: idempotent, auditable, dry-run capable
- Evidence captured automatically for compliance

---

## ADR-003: Module Portfolio

**Date**: 2026-04-06  
**Status**: Proposed

### Planned Modules

| Module | Purpose | Phase | Dependencies |
|--------|---------|-------|--------------|
| **NinjaOne Deployment** | Software deployment, onboarding, drift | Phase 2 | Base ninja SDK |
| **Customer Offboarding** | Cross-platform termination workflow | Phase 1 | All platform handlers |
| **Google Workspace GAM** | Delegated tenant management | Phase 1 | GAM CLI in workers |
| **Microsoft CSP** | Tenant management, GDAP | Exists | Native BiFrost capability |

### Platform Handler Requirements

| Platform | Cleanup Actions |
|----------|-----------------|
| Cove | Remove backup accounts, verify no jobs |
| VIPRE | Uninstall agents, deactivate licenses |
| Huntress | Uninstall EDR, unmap identity |
| ConnectSecure | Remove customer, decommission scanners |
| Meraki | Inspect devices, decommission org |
| NinjaOne | Remove agents, clear custom fields |
| Datto RMM | Remove agents (transitional) |

---

## ADR-004: Legacy PlatformAdapters Pattern

**Date**: 2026-04-06  
**Status**: Superseded

### Context
`code/PlatformAdapters/` was created for PowerShell module wrappers with normalization layers.

### Decision
**Superseded by BiFrost service layer.** Platform adapters in agents repo are now legacy/testing artifacts.

### Migration Path
- Existing PowerShell scripts: Keep for workstation-level automation
- New platform integration: Build as BiFrost `api/shared/` service client
- NinjaOne/HaloPSA SDKs: Use `modules/ninjaone.py`, `modules/halopsa.py` directly
