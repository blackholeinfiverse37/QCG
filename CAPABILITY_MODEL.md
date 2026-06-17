# CAPABILITY_MODEL.md

> Capability Registry Foundation — Phase 1
> Single source of truth for what a capability is in BHIV systems.

---

## What Is a Capability?

A **capability** is a well-defined, reusable, scope-bounded function that a
system can offer or consume through a declared interface.

A capability:
- Has an explicit owner
- Declares its inputs, outputs, and authority limits
- Specifies how it attaches to a consumer (embedded, API-linked, sidecar, etc.)
- Is versioned and status-tracked
- Is independent of any single product's business logic

---

## Required Distinctions

### Capability ≠ Product

| Capability | Product |
|------------|---------|
| Scope-bounded, reusable function | Business-facing deliverable |
| Declares inputs/outputs explicitly | May aggregate many capabilities |
| No product-specific logic | Owns product lifecycle |
| Adoptable by any BHIV product | Specific to one domain or customer |

A product *uses* one or more capabilities. A capability does not belong to a
product — it belongs to an owner and is consumed by products.

---

### Capability ≠ Team

| Capability | Team |
|------------|------|
| A structural function in the system | A human organizational unit |
| Versioned, schema-validated artifact | Managed by org chart |
| Discoverable via registry | Discoverable via HR/org tooling |
| Has attachment rules and authority limits | Has reporting lines and headcount |

A team may *own* a capability, but the capability is a system artifact, not the
team itself. Ownership is a declared field, not an identity.

---

### Capability ≠ Authority

| Capability | Authority |
|------------|-----------|
| A function that can be invoked | The right to make a decision or enforce policy |
| Declares what it does | Declares what it controls |
| Has consumers | Has jurisdiction |
| Can be attached or detached | Is structural and non-transferable |

A capability may *require* authority to invoke (declared in `authority_limits`),
but the capability itself is not the authority. Governance decisions, execution
rights, and policy enforcement are authority concerns — not capability concerns.

This mirrors the authority boundary pattern established in `governance_authority.py`:
GovernanceLayer owns policy enforcement; a "governance capability" would be the
reusable function a product attaches to access that enforcement — they are not
the same thing.

---

## Capability Lifecycle States

| Status | Definition |
|--------|------------|
| `DRAFT` | Schema defined, not yet validated or available for adoption |
| `ACTIVE` | Validated, available for consumer attachment |
| `DEPRECATED` | Still functional, replacement exists, consumers must migrate |
| `RETIRED` | No longer available for new attachments |

---

## Capability Scope Levels

| Scope | Definition |
|-------|------------|
| `SYSTEM` | Available across the entire BHIV ecosystem |
| `DOMAIN` | Available within a specific domain (e.g., execution, trust, communication) |
| `PRODUCT` | Available only within a single product boundary |
| `EXPERIMENTAL` | Available for evaluation; no stability guarantee |

---

## Formal Capability Definition

```
Capability := {
    identity:     (capability_id, capability_name, version, owner)
    status:       (status, scope)
    interface:    (inputs, outputs, dependencies)
    attachment:   (attachment_rules, consumers)
    authority:    (authority_limits)
    reference:    (documentation_reference)
}
```

A capability record is immutable after reaching `ACTIVE` status. Version
increments produce a new record; the old record moves to `DEPRECATED`.

---

## What a Capability Does NOT Own

A capability declaration explicitly excludes:

- **Governance decisions** — who may invoke the capability is declared in
  `authority_limits`, but enforcement is the consumer's governance layer
- **Runtime execution authority** — a capability describes a function; it does
  not grant the right to execute arbitrary code in a consumer's runtime
- **Product-specific business logic** — capabilities are reusable; any logic
  that only applies to one product belongs in that product, not the capability
- **Dashboard implementation** — observability surfaces are consumers of
  capability outputs, not part of the capability definition itself

---

## Relationship to Existing QCG Patterns

| QCG Concept | Capability Registry Equivalent |
|-------------|-------------------------------|
| `AuthorityDeclaration` in `governance_authority.py` | `authority_limits` field in capability record |
| `SemanticEntry` in `semantic_registry.py` | `capability_name` + `documentation_reference` |
| `attachment_point` column in `ARCHITECTURE.md` | `attachment_rules` field in capability record |
| `status` in `execution_contract.py` | `status` field (ACTIVE/DEPRECATED/RETIRED) |
| `dependencies` in contract pipeline | `dependencies` array in capability record |

The capability registry is a discovery and contract layer — it does not replace
any existing QCG component. It describes what each component exposes so that
other BHIV products can adopt it without reading source code.
