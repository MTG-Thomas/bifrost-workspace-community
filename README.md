# Bifrost Community Workspace

A community [Bifrost](https://github.com/jackmusick/bifrost) workspace for MSPs. Contains modules, AI agents, workflows, and apps that can serve as references or be ported into your own workspace.

> **Note:** This repo is meant as a starting point and reference, not a fork-and-run solution. The recommended approach is to use an AI agent to port the pieces you need into your own Bifrost workspace, adapting them to your environment as you go.

## What's Included

### Features

**HaloPSA Report Agent** — An AI agent that generates HaloPSA SQL reports from natural language. Searches its knowledge base for schema patterns, writes and executes queries, iterates on errors, and saves what it learns for next time.

**Microsoft CSP App** — A React application for managing Microsoft CSP tenants. Links tenants to Bifrost organizations, handles application consent, manages GDAP relationships and role assignments, and provides batch operations.

**AutoElevate Integration** — An AI agent that reviews AutoElevate privilege elevation requests against your approval policy and autonomously approves, creates rules, or escalates to a human tech.

### Modules (MSP Integration SDKs)

| Module | Description |
|--------|-------------|
| `modules/halopsa.py` | HaloPSA PSA platform |
| `modules/autoelevate.py` | AutoElevate privilege elevation (with TOTP MFA) |
| `modules/ninjaone.py` | NinjaOne RMM |
| `modules/huntress.py` | Huntress EDR |
| `modules/itglue.py` | IT Glue documentation (US/EU/AU) |
| `modules/pax8.py` | Pax8 distributor (OAuth2) |
| `modules/cove.py` | Cove Data Protection / N-able Backup |
| `modules/sendgrid.py` | SendGrid email |
| `modules/immybot.py` | ImmyBot software deployment |
| `modules/microsoft/` | Microsoft Graph, CSP, GDAP, Exchange, Auth |

### Extension Helpers

| Extension | Description |
|-----------|-------------|
| `modules/extensions/halopsa.py` | Pagination, enriched tickets, batch ops, SQL execution, ticket creation |
| `modules/extensions/ninjaone.py` | Remote PowerShell execution via fetch-and-execute pattern |
| `modules/extensions/sendgrid.py` | Higher-level email sending with integration config |
| `modules/extensions/permissions.py` | Bifrost RBAC role-checking and authorization |

### Shared Tools

- **HaloPSA tools** — Auth-checked ticket operations, notes, agreements, time entry
- **Microsoft tools** — Email via Graph API, Exchange data providers
- **Bifrost utilities** — Organization management, role management, permissions

## Usage

The recommended way to use this repo is to have an AI agent (e.g., Claude Code with the Bifrost skill) read the code here and port the relevant pieces into your own workspace. This lets you adapt modules, workflows, and patterns to your specific environment rather than trying to maintain a fork.

For Bifrost documentation, see [docs.gobifrost.com](https://docs.gobifrost.com).

### Configuration Reference

Key config values used by included features:

| Config | Used By | Description |
|--------|---------|-------------|
| `autoelevate_approval_policy` | Elevation Agent | Your approval policy text |
| `autoelevate_approval_email_template_id` | Elevation Agent | HaloPSA email template for approvals |
| `autoelevate_denial_email_template_id` | Elevation Agent | HaloPSA email template for denials |
| `ninja_script_id` | NinjaOne Extension | Pre-deployed script ID for remote execution |

The Microsoft CSP app also needs a `RESELLER_LINK` in `apps/microsoft-csp/components/TenantTable.tsx` set to your Partner Center reseller invitation URL.

## Contributing

Contributions are welcome! If you've built something useful on Bifrost, consider adding it here.

1. Fork the repo
2. Create a feature branch
3. Add your module, workflow, or app
4. Submit a pull request

Please ensure any contributed code is generalized (no org-specific IDs, credentials, or customer data).

## License

MIT
