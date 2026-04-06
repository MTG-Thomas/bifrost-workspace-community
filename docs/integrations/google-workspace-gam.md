# Google Workspace GAM Module

## Overview

A BiFrost module for managing Google Workspace tenants via GAM (Google Apps Manager). Supports both direct tenant management and delegated reseller scenarios.

## Scope

### Phase 1: Read-Only Discovery (Current)
- [ ] Tenant documentation exports
- [ ] User inventory with license states
- [ ] Group membership reports
- [ ] Security settings baseline

### Phase 2: Write Automation (Future)
- [ ] User onboarding/offboarding
- [ ] License provisioning
- [ ] Group membership management
- [ ] Device management

## Architecture

### Module Structure

```
modules/google_workspace.py      # SDK wrapper for GAM CLI
apps/google-workspace-admin/   # React technician UI
features/gam_workflows/        # Bifrost workflows
```

### GAM Execution Patterns

| Context | Pattern | Auth |
|---------|---------|------|
| **Direct tenant** | GAM with service account | Stored credential |
| **Delegated (reseller)** | GAM with admin OAuth | OAuth2 refresh token |

Both patterns wrap GAM CLI execution via subprocess with:
- Structured output (CSV/JSON)
- Error handling and retry
- Audit logging

## Use Cases

### 1. Onboarding Discovery

New customer with Google Workspace → Run discovery workflow:
- Export all users and their licenses
- Document group structures
- Capture security settings baseline
- Store in IT Glue/HaloPSA

### 2. Offboarding Execution

Customer termination → Run offboarding workflow:
- Suspend user accounts
- Transfer Google Drive data to admin
- Revoke all mobile devices
- Export audit logs
- Remove licenses

### 3. License Optimization

Monthly → Run license report:
- Identify inactive users (>90 days)
- Flag unassigned licenses
- Recommend license tier changes

## Integration Points

- **BiFrost Secrets**: GAM credentials per tenant
- **HaloPSA**: Ticket creation for manual steps
- **IT Glue**: Documentation export target
- **Customer Offboarding**: Called as sub-workflow for Google cleanup

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| GAM CLI version drift | Pin version in container image |
| OAuth token expiration | Automated refresh + alerting |
| Rate limiting | Exponential backoff + queue |
| Wide-scope OAuth | Limit to required scopes only |

## Dependencies

- GAM CLI installed in BiFrost worker containers
- Service account keys or OAuth credentials in Key Vault
- Google Workspace admin access (direct or delegated)

## Related

- See `customer-offboarding.md` - Google Workspace handler is a sub-component
- See `integrations/google-workspace/` in agents repo for GAM architecture research
