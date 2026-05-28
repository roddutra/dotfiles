---
name: crm-foundation
description: Patterns and constraints for the PRD-016 CRM foundation (Client, Client Company, Enquiry, audit pipeline, resolvers, access model). Load when editing files under apps/api/app/{Models/Tenant, Services/Crm, Services/Enquiry, Http/Controllers/Crm, Policies/Crm}, or under apps/api/resources/js/pages/{clients,client-companies,enquiries,triage}, or when working on tests under tests/Feature/Crm/* or tests/Architecture/{CrmBoundariesTest,UuidV7GenerationTest,Enquiry*,Crm*}.
---

# CRM Foundation

On-demand context for the PRD-016 surface. For the full architecture, read `apps/api/docs/architecture/crm-foundation.md`.

## Write boundaries

### `Enquiry::$vertical_data` - three legal writers

1. `App\Models\Tenant\Enquiry::save()` invoked from `App\Services\Crm\EnquiryResolver::findOrCreate(...)` (insert path).
2. `App\Models\Tenant\Enquiry::saveForPromotion(Closure $mutator)` invoked from `App\Services\Enquiry\EnquiryPromotionService::promote(...)` (post-creation mutation path).
3. `App\Models\Tenant\Enquiry::transitionToSubstate(string $substate, ?string $actorId = null)` (lifecycle transitions).

Direct assignment, `setAttribute`, `fill`, `forceFill`, `Arr::set`, raw `DB::table('enquiries')->update(...)`, `unguarded(...)`, and `withoutEvents(...)` are blocked by `tests/Architecture/EnquiryVerticalDataWriteBoundaryTest`. Add new bypass shapes to `tests/Fixtures/ArchitectureBypasses/vertical_data.php` first.

### `enquiry_events` - two legal writers

- `App\Services\Enquiry\EnquiryEventWriter::recordToolMilestone(Enquiry, array $payload)` writes `tool_milestone` rows.
- `App\Services\Enquiry\EnquiryEventWriter::recordPromotion(Enquiry, array $promotedPaths, array $toolContext)` writes `tool_promotion` rows.
- `App\Models\Tenant\Enquiry::transitionToSubstate(...)` writes `lifecycle_transition` rows.

Both `EnquiryEventWriter` methods assert `DB::transactionLevel() >= 1` on the tenant connection. Enforced by `tests/Architecture/EnquiryEventsWriteBoundaryTest`.

### `crm_audit_events` - one legal writer

`App\Services\Crm\CrmAuditWriter` is the only writer. Enforced by `tests/Architecture/CrmAuditEventsWriteBoundaryTest`.

## Adding a new audited mutation

```
route -> controller -> Form Request -> domain mutation -> CrmAuditWriter::write(AuditActor, ...)
```

1. Add the route to `apps/api/routes/crm.php` inside the existing middleware group.
2. Controller goes under `apps/api/app/Http/Controllers/Crm/`.
3. Validate via a Form Request, never inline.
4. Authorise via `Gate::authorize(...)` against the matching policy under `apps/api/app/Policies/Crm/`.
5. Pass an explicit `AuditActor::tenantStaff($user, $membership)` or `AuditActor::publicCapture($sessionId)` to `CrmAuditWriter` - never rely on `CurrentActorResolver` defaulting.
6. Bulk operations: write a parent `crm_audit_events` row, then set `parent_audit_id` on the children. See `BulkReassignController` for the reference shape.

## Capability gate pattern

Server-side: `Gate::authorize('viewAny', Enquiry::class)` or the matching policy method. Policies live at `apps/api/app/Policies/Crm/*Policy.php` and all defer to `App\Services\Crm\CrmAccessResolver`.

UI-side: `permissions.crmCapabilities` is an Inertia shared prop carrying the flattened CRM capability set (`crm.triage.view`, `crm.triage.claim`, `crm.triage.assign`, `crm.records.manage_all`, `crm.enquiries.reassign`). Use it to hide actions the user lacks - never as a substitute for the server check.

## Resolver pattern

`App\Services\Crm\ClientResolver`, `ClientCompanyResolver`, and `EnquiryResolver` all expose `findOrCreate(...)` returning `App\Services\Crm\ResolverResult` with a `ResolverMode`:

- `Created` - new row inserted.
- `Attached` - existing row matched deterministically.
- `Suggested` - multiple candidates; redacted list returned for the caller to disambiguate.

Tenant Staff create paths (forms, admin UIs) pass `forceCreate: true` to skip the `Suggested` branch. Public-capture paths (Scout submission, future Tool inbound) leave the default `false`.

`EnquiryResolver` additionally takes an optional `EnquiryContinuationProof` for public-capture continuation. PRD-016 ships only the interface; the first Tool that needs continuation owns its real implementer.

## Architecture-bypass fixture pattern

When you find a new way to bypass a write boundary, do this first:

1. Add the bypass shape to `apps/api/tests/Fixtures/ArchitectureBypasses/<boundary>.php`.
2. Run the matching architecture test - it must fail.
3. Plug the production gap so the test goes green.

This keeps the bypass list authoritative. The reverse order ("fix code, then maybe add a test") drifts.

## Tool table anchor

Every Tool interaction / snapshot table MUST carry an `enquiry_id` foreign key and a `BelongsTo enquiry()` relationship on its model. Pattern names checked: `*_submissions`, `*_snapshots`, `*_interactions`, `*_conversations`, `*_runs`, `*_attempts`, `*_uploads`.

Config tables (`*_configs`) are excluded via `apps/api/tests/Fixtures/Architecture/tool-config-tables.php`. Enforced by `tests/Architecture/ToolTablesEnquiryAnchorTest`.

## Central-connection pin

`App\Models\TenantMembership`, `App\Models\User`, and `App\Models\CentralUser` all set `protected $connection = 'pgsql'`. Inside `tenancy()->initialize(...)`, the default connection is `tenant` - querying these models without the pin (or without `->on('pgsql')`) hits the wrong database.

PRD-016 Slice 4 shipped a production regression here because the test harness aliases `tenant` back onto central `pgsql` and masked the bug. The regression cover is `tests/Feature/Crm/AccessControl/PolicyTenantContextTest` - keep it green.

## Pointers

- Architecture overview: `apps/api/docs/architecture/crm-foundation.md`
- Tool data contract (payload shapes, transaction guarantees): `apps/api/docs/guides/prd-016-tool-data-contract.md`
- Public capture security (throttle, tenant resolution, allow-list): `apps/api/docs/guides/prd-016-public-capture-security.md`
- Lifecycle states: `apps/api/docs/architecture/lifecycle-states.md`
- Original design rationale: `apps/api/docs/specs/PRD-016-client-enquiry-foundation.md`
