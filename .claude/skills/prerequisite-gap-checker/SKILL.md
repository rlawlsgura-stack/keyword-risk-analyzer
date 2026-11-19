---
name: prerequisite-gap-checker
description: "Read a task page (tutorial, how-to, quickstart, setup guide) as a reader with no prior context and list the accounts, credentials, permissions, installed tools, existing resources, and earlier steps the page assumes but never tells the reader to set up. Use when a writer asks whether a page is missing prerequisites, what a new user or an AI agent might get stuck on, or to review a tutorial or quickstart before publishing. Reports each assumption as stated, linked, late, or missing."
---

# Prerequisite gap checker

A task page has a prerequisite gap when a step only works if the reader already has something, or has already done something, that the page never mentions. Writers rarely see these gaps because they already have the setup. Models miss them for the same reason: they fill the gap from background knowledge without noticing it was missing. This check works by listing the assumptions explicitly before judging them.

## Read the page cold

If you can start a subagent, give it only the page text and these instructions, and run the check there. If you are that subagent, or cannot start one, run the check yourself. Do not start another subagent.

A subagent keeps other docs out, but it is the same model and still knows how similar products usually work. So every flag needs evidence on the page. Flag an assumption only when the page shows that a step needs it: a command the step runs, a value or variable it uses, a resource it acts on, or a requirement the page mentions anywhere. If the page shows the need and never provides it, flag it, even if you could guess the answer. If the need comes only from what you know about similar tools, such as a role, a plan, network access, or a token scope the page never mentions, do not flag it.

## Steps

1. **Find the task and the end state.** Write one sentence: what the reader should have when they finish.
2. **List assumed state for each step.** For every step, ask what must already be true for the step to work. Check these categories:
   - Accounts and access: a sign-up, an organization, an invite
   - Credentials: API keys, tokens, passwords, and where to get them
   - Permissions and plan: a role, an admin right, a paid plan or feature flag, only when the page mentions one
   - Installed tools: a CLI, a runtime, a package, and the version if it matters
   - Environment: environment variables, working directory, config files
   - Existing resources: a project, repo, space, database, or record the step acts on
   - Earlier steps: things done on another page, or values from an earlier step
3. **Classify each item.**
   - **Stated:** the page says to have or do it before the step that needs it
   - **Linked:** the page links to where it is covered, before the step that needs it
   - **Late:** the page mentions it, but only after the step that needs it
   - **Missing:** the page never mentions it
4. **Rate each Late or Missing item.**
   - **Blocks:** the step fails or cannot be started without it
   - **Slows:** the reader can probably work it out, but has to stop and search
5. **Drop noise.** Do not flag general computer skills (using a terminal, a browser, a text editor). Do not flag anything covered by an audience statement on the page, such as "This guide assumes you know Git." Count an item as Stated when the intro says the reader has it, such as "connect your site to a repo on GitHub." Do not flag wording or clarity problems, such as example values that should be placeholders, unexplained terms, or vague UI locations; those are not prerequisites. Keep one item per assumption, even if several steps need it.

## How to report

Start with the end-state sentence. Then give one table of every Late or Missing item, Blocks first:

| Step | Assumes | Status | Impact | Suggested fix |
|------|---------|--------|--------|---------------|

After the table, list Stated and Linked items in one line each, so the writer can see what the check considered.

If asked to fix the page, add or update a Prerequisites section before the first step, and move Late items there. Do not invent specifics such as a role name, a plan tier, or a version number. Write "[writer to confirm]" where the page does not give the value.

This check over-flags more than it misses. Present the results as things a reader might trip on, and let the writer decide which ones matter.
