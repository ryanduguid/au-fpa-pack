---
name: fpa-portfolio-learn
description: Use when you run FP&A for several clients and want your practice to compound - mines patterns that generalise across your same-type clients, validates them by leave-one-out cross-client backtesting, and promotes ratified priors and skills into a local library that seeds every new client. Local only, and each promotion needs an approval you record first.
---

# Portfolio learn (Loop B)

## Overview

Loop A makes the model better at one client. This makes your *practice* compound:
client #10 starts smarter than client #1 because your library carries what generalised
across #1 to 9. Everything is local - your own book, on your own machine.

**Core principle:** self-improving, never self-ratifying - propose, you accept. The
objective metric is cross-client: does a pattern learnt on some clients fail to
degrade the *others*' backtest?

**The confidentiality boundary is separate from the statistics.** Promotion moves one
client's information into other clients' work, so it is default-deny: mining and
validation propose, and nothing is written to the library until you record a
`pyfpa.PromotionApproval` for that exact candidate. "Nothing leaves your machine" is a
statement about network egress. It does not by itself permit moving Client A's
information into Client B's engagement file. Check the engagement terms and your
confidentiality obligations first. The approval you record is an acknowledgement of
that decision: it is not authentication, and it is not legal proof that the client
consented.

## Setup

A portfolio manifest `~/.fpa/portfolio.yaml` lists your clients + a business-type tag:

```yaml
library: ~/.fpa/library
clients:
  - { path: ~/clients/acme,  type: d2c-inventory }
  - { path: ~/clients/peak,  type: d2c-inventory }
  - { path: ~/clients/haul,  type: trucking }
```

## Workflow

1. **Load** the manifest (`pyfpa.load_portfolio`).
2. For each business-type with at least 3 clients:
   - **Priors:** let `type_clients = pyfpa.portfolio.clients_of_type(portfolio, type)`.
     `pyfpa.mine_priors(portfolio, type)` finds drivers that cluster tightly; validate each
     with `pyfpa.validate_prior(driver, type_clients, candidate=candidate)` (leave-one-out).
     Pass the candidate: the result then carries its digest, and `promote_prior` refuses a
     result that does not. Surface validated ones first (by cross-client delta), then
     unvalidated/judgment.
   - **Skills:** `pyfpa.find_recurring_skills(portfolio, type)` for recurring generated
     skills. Also weigh recurring **structural corrections** across clients (read each
     `.fpa/corrections/` for `type: structural`) - a human-authored pattern that repeats
     is strong signal.
3. **Present** candidates ranked by evidence (support count + cross-client delta), each
   with `pyfpa.screen_candidate(candidate)`, the automated confidentiality findings.
4. **Screen and approve.** For each candidate you accept, read the screen's findings,
   decide whether the engagement terms permit the reuse, then record one approval:

   ```python
   pyfpa.record_promotion_approval(library, pyfpa.PromotionApproval(
       purpose="Reuse an inventory-days prior across same-type engagements",
       scope=pyfpa.ApprovalScope(business_type=type, driver=candidate.driver),
       contributing_workspaces=candidate.support,
       authorisation_reference="EL-2026-014 cl 8 and practitioner sign-off",
       candidate_digest=pyfpa.candidate_digest(candidate),
       confidentiality_review=pyfpa.ConfidentialityReview(
           reviewer="<you>", reviewed_on="<ISO date>", notes="<why this is permitted>",
           automated_checks=pyfpa.screen_candidate(candidate)),
       approved_by="<you>", approved_at="<ISO timestamp>",
       allowed_files=["SKILL.md"],   # promote_skill copies nothing else
   ))
   ```

   An approval is written under `<library>/approvals/<digest>.yaml`, one per candidate,
   and it is never created for you. Change the candidate and the digest changes, so the
   old approval no longer covers it. Pass paths or ids to `contributing_workspaces`:
   the file stores opaque ids either way, so the approval names no client directory.
   Validate and promote in the same session, because `validate_prior` stamps its result
   for this process only.
5. **Ratify.** With the approval recorded, `pyfpa.promote_prior` / `pyfpa.promote_skill`
   writes `~/.fpa/library/` and `library-log.md`, naming workspaces only by an opaque id.
   `pyfpa.withdraw_prior(library, digest)` removes a prior and returns the client
   workspaces it had already seeded, so you can review what derives from it. It changes
   nothing inside those workspaces.

## Guardrails

- Local-only; nothing phones home. That is about egress, not about confidentiality
  between your clients: see the boundary above.
- Default-deny promotion. `promote_prior` refuses unless a recorded approval covers the
  candidate's digest, lists exactly its contributing workspaces, names the same business
  type and driver, and the validation carries the same digest and `validate_prior`'s
  stamp with at least 2 folds. `validate_prior` refuses a candidate whose driver,
  business type, support or value are not the ones its folds tested. `promote_skill`
  refuses any file the approval does not list, writes the bytes it screened rather than
  re-reading the client's directory, and refuses a link in the tree.
- Seeding is the same boundary in reverse: `seed_from_library` refuses a library prior
  whose approval is missing, so a legacy or hand-authored entry cannot seed a client.
  Withdraw it or record its approval.
- The gate is a structural barrier, not a security control. It stops mistakes and
  results carried in from elsewhere; it does not defend against code running in your
  own session, and it never replaces your reading of the evidence.
- The confidentiality screen looks for ABN and TFN shaped numbers, email addresses,
  phone numbers, BSB and account patterns, dollar amounts in narrative lines and the
  contributing clients' business names. A finding blocks promotion until your review
  records it. It assists your review and proves nothing: a clean screen is not a finding
  that no client information is present.
- At least 3 distinct client workspaces to propose; tight-cluster only; a prior must not
  degrade held-out clients. A manifest that names the same workspace twice is rejected,
  so support counts and validation folds stay independent. The gate then counts distinct
  clients by business-profile heading, normalised for case, punctuation, bracketed
  qualifiers and entity suffixes, so `Joinery Pty Ltd` and `Joinery (Newcastle)` are one
  client. A workspace with no heading establishes no client. Promoting across two
  workspaces that normalise to one name takes both workspace ids in
  `aliases_acknowledged` plus review notes saying why they are separate; notes alone are
  not enough.
- You ratify everything; priors are *seeds*, not mandates - each client's Loop A refines.

## The payoff

New clients inherit the library: **fpa-learn-business** seeds their starting model from
your promoted priors (`pyfpa.seed_from_library`) and offers the promoted skills. Each
seeding is recorded in the receiving workspace's `.fpa/library-seeds.yaml` and in the
library's `provenance/seeds.yaml`, which is what makes a later withdrawal traceable.

## Next

Promoted → the next new client onboarded via **fpa-learn-business** starts smarter.
