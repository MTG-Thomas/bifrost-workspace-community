# NinjaOne Deployment & Onboarding Module

## Overview

A BiFrost application module that replaces core ImmyBot workflows for Midtown MSP:
- Software deployment with version control
- New device onboarding with standardized profiles  
- Desired-state enforcement with drift detection and remediation

## Architecture

### Module Structure

```
apps/ninjaone-deployment/
├── api/
│   ├── src/handlers/
│   │   ├── packages.py        # Package catalog CRUD
│   │   ├── profiles.py        # Onboarding profile management
│   │   ├── deployments.py     # Deployment execution
│   │   └── drift.py           # Drift detection & remediation
│   └── shared/
│       └── ninjaone_client.py # Platform adapter wrapper
└── client/
    └── src/components/
        ├── PackageLibrary/
        ├── ProfileBuilder/
        └── DeploymentDashboard/
```

### Key Capabilities

| ImmyBot Concept | BiFrost Implementation |
|----------------|------------------------|
| Software Library | BiFrost-managed package catalog + NinjaOne automation scripts |
| Onboarding Profiles | BiFrost manifest + ordered actions (policies + custom fields) |
| Desired State | Scheduled BiFrost drift evaluator (4hr loop) + remediation queue |

### Integration Points

- **NinjaOne API**: Automation scripts, device queries, policy overrides
- **Azure Key Vault**: Secret management for OAuth credentials
- **BiFrost Integrations**: Tenant mapping, org scoping, execution logging

## Gaps & Workarounds

| Gap | Workaround |
|-----|------------|
| No first-class package catalog | BiFrost-side manifest with version rules + detection logic |
| No native "profile" object | BiFrost-managed manifest + ordered actions |
| No continuous desired-state engine | BiFrost scheduler + drift loop + approval workflow |

## Implementation Phases

### Phase 1: Foundation (Complete)
- [x] BiFrost PoC deployed
- [x] k8s manifests stabilized (Docker Hub images)
- [x] RabbitMQ/Redis secrets patched
- [x] NinjaOne API mapping documented
- [x] Base ninja module operational

### Phase 2: Core Module (Next)
- [ ] Extend ninja module with package catalog handlers
- [ ] Add onboarding profile data models
- [ ] Build technician-facing React components for deployment
- [ ] Integrate with "Customer Offboarding" meta-workflow

### Phase 3: Execution (Pending)
- [ ] Deployment queue integration (RabbitMQ)
- [ ] Drift detection scheduler
- [ ] Remediation workflow with approval gates
- [ ] Evidence capture for audit trail

### Phase 4: Hardening (Future)
- [ ] Azure Container Apps migration
- [ ] Multi-region failover
- [ ] Git-backed manifest round-trip

## Migration from Current State

| Current | Target |
|---------|--------|
| ImmyBot packages | Import to BiFrost catalog |
| PowerShell scripts | Convert to NinjaOne automation scripts |
| Technician PS execution | BiFrost web UI + approval workflow |
| Manual drift checks | Scheduled BiFrost evaluator |

## Dependencies

- **BiFrost Core**: PoC deployed, ninja module exists and operational
- **NinjaOne API**: OAuth integration documented
- **Azure Key Vault**: Secrets management in place
- **Customer Offboarding**: Related meta-workflow - shares platform adapter patterns

## Success Criteria

1. Technician can deploy software to 10+ devices without PowerShell
2. New device onboarding completes with <5 UI interactions
3. Drift detection identifies 95%+ of software variance within 4 hours
4. All actions auditable via BiFrost execution logs

## Related Modules

| Module | Purpose | Status |
|--------|---------|--------|
| **NinjaOne Deployment** | Software deployment, device onboarding | Phase 2 (this proposal) |
| **Customer Offboarding** | Cross-platform customer termination workflow | Reference implementation: Wyndham |
| **Google Workspace GAM** | Delegated tenant management | Phase 1 |
| **M365 GDAP** | Cross-tenant Graph operations | Native BiFrost capability |

## References

- `modules/ninjaone.py` - Base SDK
- `modules/extensions/ninjaone.py` - Extension helpers (remote PowerShell)
