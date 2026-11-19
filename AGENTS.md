# AGENTS.md: OpenAI/Codex in ODBA

## Scope and authority

This is the Codex counterpart to the pilot rules in `CLAUDE.md`. Peter's
[approval](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/121536513?focusedCommentId=123535361)
covers the two first-test documentation tickets only. These rules govern
that test and do not start the wider pilot, approve the Phase 2 split, or
supersede the [standing governance](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/56066080)
outside an explicitly approved pilot scope. Read the Jira ticket and its
comments before work. Preserve existing engineering, data and provenance controls.

## Ownership and pickup

- Jira is the source of truth for scope, readiness, ownership and decisions.
  No ticket, no work. Scheduled checks act only on explicitly approved,
  unblocked work assigned to the checking provider. Do not pick up other
  Phase 2 items from this test.
- Each ticket has one builder and the other provider as independent reviewer.
  Claude coordinates the board and reconciles it with GitHub. Use
  `builder:openai` or `builder:claude` and an attributed Jira claim; both
  providers may act under Peter's account, so account identity alone is
  not evidence of independence. Reviewers do not push to the builder's branch.
- A build goes Ready → In Progress → Review, then Done only after Peter's
  merge is recorded. If changes are requested, return to In Progress when
  the workflow allows, or record that corrections are pending in Review.
- Either provider may draft designs. Flag schema, identifiers, parsers,
  source meaning and canonical pipeline decisions with `design-review`.
  Research → Review is for the design artifact; return to Research for
  revisions. Peter's explicit Jira design approval is required before
  Ready for build. An AI verdict is not that approval, and research-only
  items never become build work just by passing review.
- Research tickets close only on Peter's written approval (Peter,
  2026-11-19, [Pilot daily log](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/122093569?focusedCommentId=125566977)).
  The lead moves the ticket to Review for the reviewer. After the
  reviewer's APPROVE it stays in Review until Peter posts his written
  approval on the ticket; then the lead moves it to Done. His written
  approval plays the part his merge plays for build tickets.

## Branch, test and review

- Verify the ticket's pinned base SHA against the intended GitHub base before
  starting. Report drift rather than silently substituting another base. Use
  one ticket and one PR per change; prefer `dbdp-NN-short-description` and put
  the ticket key in the PR title. Keep PRs draft for the handoff.
- The builder verifies the diff, runs the ticket's checks and records the PR,
  full head SHA, check results and skip reasons in the PR and Jira. For this
  docs test, attach the exact Markdown file to Jira. If attachment is
  unavailable, link the exact-commit file and record the limitation. Then
  request the independent review and place the ticket in Review.
- The reviewer verifies the exact PR head, checks scope and independently
  runs the applicable tests. Do not pass a missing required check.
  Record `OPENAI BUILDER CHECK: PASS @ <full sha>` or the Claude equivalent.
  The other provider posts an attributed `CLAUDE VERDICT` or `OPENAI VERDICT`
  with APPROVE or CHANGES REQUESTED, exact SHA, checks, and any limitations
  on the PR itself and mirrors it in Jira. Where a native review is
  unavailable or does not show independence, use an attributed PR comment.
- Dual sign-off means a builder PASS and the other provider's APPROVE on
  the same full head SHA, with no unresolved must-fix. A new commit
  invalidates both receipts and requires fresh checks and sign-off. If
  main moves and the branch is updated, apply the same rule.
- After two correction rounds, or immediately for a scope/design dispute
  or an unavailable required check, record `needs-peter` in Jira and on
  the PR with the decision needed. Use Jira or the
  [Pilot daily log](https://fmtransformation.atlassian.net/wiki/spaces/ODBA/pages/122093569)
  for coordination so Peter does not have to relay routine handoffs.

## Human merge gate

Peter alone decides and admin-merges. Neither provider merges, enables
auto-merge, changes branch protection, or pushes to main. Keep review
evidence on the PR and in Jira; the merge commit is the Done receipt.
Do not start additional work from this documentation test without explicit
authorization.
