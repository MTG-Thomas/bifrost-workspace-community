# Customer Offboarding Meta-Workflow

## Overview

A BiFrost workflow that orchestrates customer termination across all integrated platforms. Uses the Wyndham offboarding as the reference implementation.

## Problem Statement

Customer offboarding currently requires manual cleanup across multiple platforms:
- Backup systems (Cove/Datto)
- Security tools (VIPRE, Huntress, ConnectSecure/CyberCNS)
- Network infrastructure (Meraki)
- RMM agents (NinjaOne, Datto RMM)
- Documentation systems (IT Glue, etc.)

This is error-prone, time-consuming, and lacks centralized audit trails.

## Target Outcome

A repeatable BiFrost meta-workflow that:

1. **Enumerate** customer assets across all integrated platforms
2. **Queue** decommissioning jobs per platform
3. **Capture** evidence of removal
4. **Notify** stakeholders via runbook execution
5. **Audit** all actions via BiFrost execution logs

## Workflow Stages

```
┌─────────────────┐
│  1. Trigger     │ ← HaloPSA ticket / scheduled / API
│  (Customer ID)  │
└────────┬────────┘
         ▼
┌─────────────────┐
│  2. Discover    │ ← Query all platforms for customer assets
│    Assets       │
└────────┬────────┘
         ▼
┌─────────────────┐
│  3. Confirm     │ ← Technician review + approval
│   Scope         │
└────────┬────────┘
         ▼
┌─────────────────┐
│  4. Queue Jobs  │ ← Enqueue platform-specific removals
│  (RabbitMQ)     │
└────────┬────────┘
         ▼
┌─────────────────┐
│  5. Execute     │ ← BiFrost workers process removals
│   Removals      │
└────────┬────────┘
         ▼
┌─────────────────┐
│  6. Verify      │ ← Confirm assets removed
│   & Evidence    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  7. Close       │ ← Update PSA, notify stakeholders
│   & Notify      │
└─────────────────┘
```

## Platform Handlers

| Platform | Handler Location | Cleanup Actions |
|----------|-------------------|-----------------|
| **Cove** | `handlers/cove.py` | Remove backup accounts, verify no active jobs |
| **VIPRE** | `handlers/vipre.py` | Uninstall agents, deactivate licenses |
| **Huntress** | `handlers/huntress.py` | Uninstall EDR, unmap identity integration |
| **ConnectSecure** | `handlers/connectsecure.py` | Remove customer, decommission scanners |
| **Meraki** | `handlers/meraki.py` | Inspect devices, decommission org if owned |
| **NinjaOne** | `handlers/ninjaone.py` | Remove agents, clear custom fields |
| **Datto RMM** | `handlers/dattormm.py` | Remove agents (migration transitional) |

## Reference Implementation: Wyndham

The Wyndham offboarding issues (#51-58, #80, #82) serve as requirements for the first implementation:

- ~~Remove Cove devices~~ → `cove.py` handler
- ~~Remove ConnectSecure footprint~~ → `connectsecure.py` handler  
- ~~Uninstall VIPRE~~ → `vipre.py` handler
- ~~Uninstall Huntress EDR~~ → `huntress.py` handler
- ~~Meraki inspection/decommission~~ → `meraki.py` handler
- ~~Datto agent removals~~ → `dattormm.py` handler
- ~~Customer communications~~ → notification workflow step

## Integration with NinjaOne Deployment Module

The offboarding workflow reuses the same platform adapter pattern as the NinjaOne deployment module:

- Shared `ninjaone_client.py` for API interactions
- Same RabbitMQ job queue infrastructure
- Same evidence capture and audit trail patterns

## Technical Requirements

1. **Idempotent handlers** - Running twice shouldn't fail or double-remove
2. **Evidence capture** - Screenshots/API responses stored to blob storage
3. **Failure handling** - Failed removals create tickets, don't block entire workflow
4. **Approval gates** - High-risk removals (entire org deletion) require human approval
5. **Dry-run mode** - Preview what would be removed without executing

## Next Steps

1. [ ] Build base workflow scaffold in BiFrost
2. [ ] Implement Cove handler (Wyndham reference)
3. [ ] Implement VIPRE handler with pagination fix
4. [ ] Add technician UI for offboarding initiation
5. [ ] Build verification/evidence capture system
