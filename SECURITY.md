# Security policy

## Supported versions

Security fixes are applied to the latest version on the default branch.

## Reporting a vulnerability

Use this repository's private vulnerability-reporting feature (Security >
Report a vulnerability). Do not open a public issue or pull request for a
suspected vulnerability.

Include a clear description, reproduction steps using fabricated data, likely
impact, and any suggested mitigation. Never include client, taxpayer,
employee, payroll, banking, access-token or other sensitive data.

A valid report will be acknowledged within 7 days. The fix and disclosure
timeline will be agreed with the reporter.

If GitHub private reporting is not visible, email is not published as a
fallback on purpose: enable private reporting in repository settings rather
than creating a public inbox.

## Upstream

au-fpa-pack is an Australian pack built on
[openfpa](https://github.com/JeffBrines/openfpa) by Guiderail. A vulnerability
in the shared `pyfpa` kernel belongs upstream. Report it to the openfpa
maintainers as well, and say here that you have done so, so the fix is not
duplicated or delayed.

## What this project does and does not do

au-fpa-pack runs locally against files you provide. It does not ship
credentials, does not authenticate to Xero or any other accounting system, and
does not post journals, lodge a BAS or a tax return, make payments, or send
client correspondence.

Generated connectors deliberately fail until a maintainer implements
host-authenticated access. That stub is a safety boundary. Do not paste
credentials into a connector, a config file, a fixture, an example, or a
prompt to reach a live system faster.

Treat every file the tool reads, and every model or agent output, as untrusted
input. Company financial data placed in a working directory stays on that
machine unless something else moves it. If a cloud AI service is pointed at
this workspace, that data passes to the service; check the firm's policy and
confidentiality obligations first, and de-identify by default.

## Cross-client promotion

"Nothing leaves your machine" is a statement about network egress. It says
nothing about confidentiality between the clients on that machine. Moving one
client's information into another client's work is a separate decision, and
`pyfpa/portfolio` treats it as default-deny.

Mining a prior or a recurring skill proposes; it does not authorise. Nothing is
written to a shared library until a practitioner records a `PromotionApproval`
bound to that exact candidate by a sha256 digest, listing the purpose, the
contributing workspaces, the authorisation it rests on, a confidentiality
review, and, for a skill, every file that may be copied. Change the candidate
and the digest changes, so an earlier approval stops covering it. Nothing
creates an approval automatically, and recording one never overwrites another.

The approval is an acknowledgement recorded by the practitioner. It is not
authentication: the kernel cannot tell who wrote the file. It is not legal proof
that the client consented, and it does not replace the engagement terms, the
firm's confidentiality policy or professional obligations.

The gate is a structural barrier inside one process, not a security boundary.
`ValidationResult` is a public model, so `validate_prior` stamps each result it
produces and `promote_prior` refuses a result that stamp does not cover: that
stops a result built by hand, edited on disk or carried over from another
candidate, and it stops nothing that runs inside the process, which can call the
same functions. Validate and promote in one session, because the stamp does not
outlive the process. A promoted skill is written from the bytes the digest and
the screen covered, not copied from the client's directory a second time, and a
symlink, junction or other reparse point in the tree is refused rather than
followed.

Reading the library is the same boundary as writing it, so seeding a client from
the library digests each stored prior again from its driver, business type, value
and contributing workspaces, and refuses it unless that reproduces the digest the
promotion recorded and the approval for that digest is on disk. A legacy or
hand-authored entry, and an entry edited after promotion, are both refused. An
approval file is located by digest and must record that same digest, so a record
copied onto another candidate's filename approves nothing.

The automated confidentiality screen looks for ABN and TFN shaped numbers,
email addresses, Australian phone numbers, BSB and account patterns, dollar
amounts in narrative lines, and the contributing clients' business names. A
finding blocks the promotion until the recorded review lists it. The screen
assists a human review and proves nothing: a clean screen is not a finding that
no client information is present, and it cannot see information it has no
pattern for.

Support is counted in distinct clients, not distinct directories. Headings from
each workspace's business profile are compared with case, punctuation, bracketed
qualifiers and entity suffixes removed, so a copied workspace cannot become a
second contributor by relabelling its profile, and a workspace with no heading
establishes no client at all. Promotion across two workspaces that resolve to
one business name requires their workspace ids in the approval's
`aliases_acknowledged`, alongside review notes.

Shared library records name workspaces by an opaque id, the approval file and
the seed index included, with the path-to-id map kept in the library's own
`provenance/` directory. Recording an approval is an exclusive create, so two
writers racing on one digest cannot both believe they recorded the decision. Seeding a new client records
the prior it used, so `withdraw_prior` can report which workspaces hold derived
artefacts. Withdrawal never deletes anything inside a client workspace; what to
do with a derived model is a practitioner's decision.

Examples and fixtures in this repository are fabricated, except where they are
drawn from published public-company filings. Never commit real client data.
