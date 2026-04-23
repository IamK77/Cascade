# Complete Examples

## Example 1: Feature Development

### Scenario
Build a new authentication feature with frontend and backend.

### Step 1: Create Task Graph

```bash
# Initialize from project root
cd /project
cascade --storage .cascade

# Root analysis task
cascade add-node --id analyze-requirements

# Design tasks
cascade add-node --id design-api --deps analyze-requirements
cascade add-node --id design-ui --deps analyze-requirements

# Implementation tasks
cascade add-node --id implement-api --deps design-api \
  --expectations '[{
    "node_id": "design-api",
    "expectation": "API specification with endpoints",
    "promise": "Working REST API endpoints"
  }]'

cascade add-node --id implement-ui --deps design-ui \
  --expectations '[{
    "node_id": "design-ui",
    "expectation": "UI mockups and component list",
    "promise": "React components with auth flows"
  }]'

# Integration
cascade add-node --id integrate --deps implement-api,implement-ui

# Testing
cascade add-node --id test-integration --deps integrate
cascade add-node --id test-e2e --deps integrate

# Deploy
cascade add-node --id deploy --deps test-integration,test-e2e
```

### Step 2: Agent 1 Works on Analysis

```bash
# Claim first task
cascade get-task --agent agent-1

# Output:
# Task: analyze-requirements (READY → ACTIVE)

# Complete with context
cascade finish-task --task analyze-requirements --success \
  --summary "Analyzed auth requirements: OAuth2 + email/password" \
  --critical '{
    "auth_methods": ["oauth2", "email"],
    "oauth_providers": ["google", "github"],
    "session_strategy": "JWT",
    "token_expiry": "1 hour"
  }' \
  --artifacts "
# Auth Requirements

## Authentication Methods
1. **OAuth2** - Google and GitHub providers
2. **Email/Password** - With email verification

## Session Management
- JWT tokens with 1-hour expiry
- Refresh tokens stored securely
- Session invalidation on password change

## Security Requirements
- Rate limiting on login attempts
- CSRF protection
- Secure cookie settings
"
```

### Step 3: Parallel Design Work

```bash
# Both design tasks now READY
cascade list-nodes --state READY
# design-api: READY
# design-ui: READY

# Agent 2 claims API design
cascade get-task --agent agent-2
# Task: design-api

# Agent 3 claims UI design
cascade get-task --agent agent-3
# Task: design-ui
```

### Step 4: Complete Designs

```bash
# Agent 2 completes API design
cascade finish-task --task design-api --success \
  --summary "API design complete with 5 endpoints" \
  --critical '{
    "endpoints": [
      "POST /auth/register",
      "POST /auth/login",
      "POST /auth/logout",
      "GET /auth/me",
      "POST /auth/refresh"
    ],
    "api_version": "v1"
  }'

# Agent 3 completes UI design
cascade finish-task --task design-ui --success \
  --summary "UI design with 3 main components" \
  --critical '{
    "components": ["LoginForm", "RegisterForm", "AuthProvider"],
    "ui_library": "shadcn/ui"
  }'
```

### Step 5: Parallel Implementation

```bash
# Both implement tasks now READY
cascade get-task --agent agent-2
# implement-api (receives context from design-api + analyze-requirements)

cascade get-task --agent agent-4
# implement-ui
```

---

## Example 2: Split and Refine

### Scenario
Realize during implementation that a task is too complex.

### Initial Setup

```bash
cascade add-node --id analyze
cascade add-node --id implement --deps analyze
cascade add-node --id test --deps implement
cascade add-node --id deploy --deps test
```

### Split During Implementation

```bash
# Agent working on implement realizes it's too big
cascade get-task --agent agent-1
# Task: implement

# After analysis, split into components
cascade split-node --parent implement --children auth,api,ui,database

# Result:
# - implement removed
# - auth, api, ui, database created (all READY if analyze is COMPLETED)
# - test now depends on ALL FOUR: auth, api, ui, database
```

### Add Missing Dependency

```bash
# Realize api needs auth first
cascade refine-node --node api --dep auth \
  --expectation "Auth middleware and tokens" \
  --promise "Will use auth tokens in API calls"

# Now graph:
# analyze → [auth → api, ui, database] → test → deploy
```

---

## Example 3: Error Recovery

### Scenario
A critical task fails.

### The Failure

```bash
# Core task fails
cascade finish-task --task core-api --fail \
  --reason "Architecture decision: need to switch from REST to GraphQL" \
  --cascade

# Result:
# core-api → FAILED
# frontend-api → CANCELLED
# integration-test → CANCELLED
# deploy → CANCELLED
```

### Recovery

```bash
# 1. Check what's cancelled
cascade list-nodes --state CANCELLED
# frontend-api, integration-test, deploy

# 2. Remove cancelled nodes
cascade remove-node --node frontend-api --cascade
# Removes frontend-api, integration-test, deploy

# 3. Create new approach
cascade add-node --id graphql-schema --deps design
cascade add-node --id graphql-resolvers --deps graphql-schema
cascade add-node --id frontend-graphql --deps graphql-schema
cascade add-node --id integration-test-v2 --deps graphql-resolvers,frontend-graphql
cascade add-node --id deploy-v2 --deps integration-test-v2
```

---

## Example 4: Multi-Agent Coordination

### Scenario
Three agents collaborating on a feature.

### Task Distribution

```bash
# Create tasks
cascade add-node --id planning
cascade add-node --id backend --deps planning
cascade add-node --id frontend --deps planning
cascade add-node --id integration --deps backend,frontend

# Agent assignments
# Agent-1: Planning (claiming first)
cascade get-task --agent agent-1
# planning → ACTIVE

# Agents 2 and 3 wait for planning to complete
# They periodically check:
cascade list-nodes --state READY
```

### After Planning Completes

```bash
# Agent-1 finishes planning
cascade finish-task --task planning --success \
  --summary "Architecture decided" \
  --critical '{"backend": "FastAPI", "frontend": "Next.js", "protocol": "REST"}'

# Now backend and frontend are READY

# Agent-2 claims backend
cascade get-task --agent agent-2
# backend → ACTIVE

# Agent-3 claims frontend
cascade get-task --agent agent-3
# frontend → ACTIVE
```

### Coordination via Context

```bash
# Agent-2 adds backend context
cascade edit-node --node backend --critical '{"api_prefix": "/api/v1"}'

# Agent-3 can check this
# (context is visible to agent-3 through integration task preview)
```

### Integration After Both Complete

```bash
# Agent-2 finishes
cascade finish-task --task backend --success \
  --artifacts "API running at localhost:8000\nSwagger at /docs"

# Agent-3 finishes
cascade finish-task --task frontend --success \
  --artifacts "Frontend running at localhost:3000\nUses /api/v1 prefix"

# integration is now READY
# Agent-1 (after finishing planning) can claim it
cascade get-task --agent agent-1
# integration → ACTIVE
```

---

## Example 5: Rework (Forward Feedback)

### Scenario
Agent discovers upstream analysis missed requirements.

### The Discovery

```bash
# Agent-2 is working on implement, discovers analyze missed OAuth
cascade get-task --agent agent-2 --task implement
# Reviews upstream context... OAuth requirements missing!

# Request rework — graph grows forward, not backward
cascade rework \
  --source analyze \
  --corrective analyze-oauth \
  --reason "Missing OAuth2 requirements for Google/GitHub" \
  --agent agent-2 \
  --source-expectation "Original analysis to review" \
  --source-promise "First analysis output" \
  --corrective-expectation "Revised analysis with OAuth2" \
  --corrective-promise "Updated requirements"

# Result:
# - analyze-oauth created (READY, depends on analyze)
# - implement goes PENDING (waiting for analyze-oauth)
# - agent-2 released from implement
```

### Completing the Correction

```bash
# Another agent picks up the corrective task
cascade get-task --agent agent-3 --task analyze-oauth
# Sees original analyze output via context propagation

cascade finish-task --task analyze-oauth --success \
  --summary "Added OAuth2: Google + GitHub via authorization code flow" \
  --critical '{"oauth_providers": ["google", "github"]}'

# implement is now READY again with corrected context
cascade get-task --agent agent-2 --task implement
# Now sees both original AND corrected requirements
```

---

## Example 6: Release and Retry

### Scenario
Task blocked on external dependency.

### The Blocker

```bash
cascade get-task --agent agent-1
# Task: implement-payment

# Realize API keys not available
cascade finish-task --task implement-payment --release \
  --reason "Waiting for Stripe API keys from finance team"

# Task back to READY, agent-1 free to work on something else
```

### Retry After Unblocked

```bash
# Later, keys received
cascade get-task --agent agent-1 --task implement-payment

# Complete
cascade finish-task --task implement-payment --success
```
