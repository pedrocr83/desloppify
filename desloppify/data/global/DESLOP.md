<!-- desloppify-deslop-begin -->
<!-- desloppify-deslop-version: 1 -->
---
name: desloppify-deslop
description: >
  Removes AI slop and unnecessary code while preserving behavior. Use when
  `desloppify next` hands you a slop, ai_generated_debt or comment_quality
  finding, when resolving any finding whose fix is a cleanup, or when the
  user asks to deslop, clean up, simplify, trim or de-bloat code, a module,
  a README or a docstring. Cuts narrating comments, dead code, unused
  imports, single-use abstractions, log-and-rethrow handlers, checks for
  impossible states, chatty logging, hand-rolled standard library and
  marketing prose. Runs the project's checks before and after, keeps
  load-bearing code, and reports what was cut, kept and flagged.
---

# Desloppify deslop

Slop is code that exists because a model wrote it by default, not because the problem needs it: comments that narrate the next line, an interface and a factory for one class, a try/except that logs and re-raises, checks for states that can't happen, "Starting..." logs, a hand-rolled `Counter`, a README that calls a file mover "blazing-fast". Each piece is small. Together they bury the code that matters and give bugs places to hide.

The job: delete what isn't pulling its weight, keep everything that is, prove behavior didn't change, and say what you did.

There are two ways to fail, and the second is worse:

- **Under-cleaning.** Cosmetic tweaks while the factory, the dead helper and the log-and-rethrow block survive.
- **Over-cleaning.** Deleting something load-bearing (a why-comment, a boundary check, a function called by name from a registry), quietly changing behavior, or churning code that was fine. A cleanup that breaks production is the most expensive slop there is.

## Scope

- The scope is the item `desloppify next` gave you: the files the finding names (`related_files` for review findings, `file` and `lines` for `slop` detector findings) and the functions those lines belong to. If the user pointed at something else, that is the scope instead. Don't sweep the repo.
- Out-of-scope slop goes in the report, one line each. Don't fix it: drive-by edits bloat the diff and hide the real change from reviewers. If it is worth fixing, it will surface as its own finding on the next scan.
- Don't change public interfaces unless asked: exported names, signatures and parameters (even unused ones), CLI flags, config keys, env vars, routes, error types or messages callers might match, log lines or metrics that alerts might read. Code you can't see depends on them. Flag them instead.
- Don't commit, amend or push unless asked. Leave the result in the working tree for the user to review.

## Workflow

1. **Baseline.** Find the checks that cover the scope (tests, type checker, linter) and run them before editing. Note anything that already fails, and note which behaviors the tests don't reach; those are the ones you'll check by hand in step 5.
2. **Read for intent (Chesterton's fence).** Read the whole target, its callers and the project's conventions (CLAUDE.md, AGENTS.md, linter config, neighboring code). Before deleting any name, search the whole repo for it as a bare word, strings included: `rg -n '\bname\b'` or `grep -rnw name .`. Code gets called through string registries, `getattr`, decorators, `__all__`, entry points, fixtures, templates and serialized data.
3. **Triage** each candidate into one bucket:
   - **Cut**: unused or redundant; removing it changes nothing observable.
   - **Simplify**: same behavior in less code.
   - **Keep**: looks like slop but is load-bearing (see "Looks like slop, isn't").
   - **Flag**: would change behavior or a public interface, or you aren't sure. Don't edit it; put it in the report with a suggestion.
   - **Out of scope**: outside the target. Don't edit it, however sloppy; list it in the report.
4. **Edit.** Make the smallest diff that removes the slop, and only inside the scope. Certain cuts first (dead code, unused imports, narrating comments), structural collapses second. Edit in place: delete lines and replace blocks with targeted edits rather than regenerating the file from memory, because wholesale rewrites are how why-comments, exact error messages and edge-case checks get lost. Match the project's style. Don't reformat lines you aren't otherwise changing, don't rename for taste, and don't add dependencies, files or new abstractions.
5. **Verify.** Re-run the step 1 checks; results should match the baseline with no test edited to get there. For each risky edit the tests don't cover (anything from "Looks like slop, isn't", any removed check or branch), run the old and new code side by side on a handful of inputs that hit that edge: 0, empty, None, duplicates, unsorted input, the error path. Keep it proportionate: three to ten hand-picked inputs per risky edit, not hundreds. Fuzzers, random-input sweeps and mutation testing are overkill for a cleanup and burn the user's time. Re-search every name you deleted. Then read the full diff as a reviewer would, walking the removed lines one by one: every removed comment should be narration, and every removed condition, message or doc line should be something you triaged as Cut. Put back anything that isn't. Also remove anything you added that is slop itself (comments about the cleanup, a new helper used once, stray blank lines). Delete throwaway scripts.
6. **Report** in your reply, using the format below, and put the one-line version in the `desloppify resolve` attestation for the finding: what was cut, what was kept on purpose, what was flagged.

If the scope turns out to be clean, say so, make the few certain cuts if there are any, and stop. Inventing work to look thorough is its own kind of slop.

## What to cut

### Comments and docstrings

Cut:
- Comments that narrate the code: `# Loop through the rows`, `// Return the result`, `# Initialize the logger`.
- Docstrings that restate the signature ("Args: rows (list): The rows. Returns: list: The result.") and JSDoc `@param`/`@returns` lines that repeat the TypeScript types.
- Section banners, emoji, changelog notes ("# Updated to use the new API"), notes to a reader ("# Note: you may want to...").
- Commented-out code. Version control has it.
- Generic TODOs ("TODO: add error handling", "TODO: optimize").

Keep:
- Why-comments: business rules, workarounds, ticket references, ordering constraints, performance or security reasons, "don't change X because Y". If a comment would stop the next person from making a mistake, it stays in the code, next to the line it explains. Mentioning it in your report doesn't count; the next reader sees the code, not your report.
- Tool directives: `# type: ignore`, `# noqa`, `// eslint-disable-next-line`, `// @ts-expect-error`, `# pragma: no cover`, `//go:build`, shebangs, license headers.
- Docstrings and field comments that state a contract the signature can't: units, defaults, what `None`, 0 or an omitted argument means, inclusive or exclusive bounds, sign conventions, side effects, raised errors, status codes. Trim the filler around the contract, keep the contract.
- TODOs with an owner, ticket or concrete condition.

### Dead and speculative code

- Unused imports, variables, private functions and methods, unreachable branches, fields written and never read, flags that are always on.
- Abstractions with one implementation and no public role: an interface plus one class plus a factory, a strategy registry with one strategy, a base class with one subclass, singletons, Manager/Helper/Service classes that only forward calls, classes with one method and no state (make them functions).
- Config objects, enums and constant classes holding one value used in one place.
- Parameters nothing passes, on private functions. On public functions, flag them.
- Demo code in library modules (`if __name__ == "__main__":` example usage, `// Example usage`) when nothing runs it. If something might, flag it.
- Compatibility shims for code that never shipped. If it shipped, it's API: flag it.

### Error handling and defensive code

Cut:
- `try`/`except` or `try`/`catch` blocks that only log and re-raise. Log once, where the error is handled.
- Checks for states the code can't reach: type checks on values your own code just built, null checks on values that can't be null, re-validation of what the caller already validated.

Keep:
- Validation at trust boundaries: user input, files, network responses, environment variables, public API arguments. Types don't stop an empty string or a negative quantity, and type hints and TypeScript types don't run at all for Python or plain-JS callers, so on a public function they never make a runtime check redundant. Keep these checks as they are: same conditions, same error types, same messages. Merging two checks (for example folding `if (!opts) throw ...` into the next check with `opts?.url`), or swapping `!x` for a `typeof` test, changes which error callers get. That is a behavior change, not a cleanup.
- Retries, backoff, timeouts, locks, idempotency keys, `finally`/`defer` cleanup. They look like ceremony and usually exist because something broke once.

Flag:
- Handlers that swallow errors (`except: pass`, `catch {}`) or rewrap them in a different type. Removing or narrowing them changes which errors callers see.

### Logging and output

Cut "Starting...", "Successfully...", "Entering function", leftover `print`/`console.log`, and the same error logged at every layer. Keep logs someone acts on (errors and warnings with context, audit events). Flag log lines a dashboard or alert might parse.

### Verbose or reimplemented code

- Loops that are really `sum`, `any`, `all`, `max`, a comprehension, `Counter`, `defaultdict`, `filter`/`map`/`some`, `Object.fromEntries`.
- `if cond: return True else: return False`, `== True`, `x = expr; return x`, `else` after `return`.
- `x !== null && x !== undefined ? x : d` becomes `x ?? d`. A Python `is not None` check stays an `is not None` check (see the traps below).
- A `new Promise` wrapped around a promise, `async` functions that only forward, `return await` outside a `try`, type annotations that repeat what is inferred, `any` where the real type is known.
- Hand-rolled helpers that duplicate the standard library or a dependency the project already has.

Don't add a dependency to delete code, and don't trade a readable block for a clever one-liner. Fewer lines is a side effect, not the goal.

### Tests

Only when tests are in scope: cut duplicated setup, narrating comments, and tests that only assert a mock returned what it was told to return. Never weaken or delete an assertion about real behavior.

### Prose in code: comments, docstrings, READMEs, changelogs, commit messages, PR descriptions, error text

- Before rewriting, list every fact in the original: commands, flags, defaults, paths, env vars, versions, platforms, exit codes, limits, license. Rewrite, then check each fact off against the new text. A fact that only lived in a cut section (a features list, a badge, an intro) moves somewhere else; it doesn't disappear. Don't add facts, features or numbers that aren't in the source.
- Cut marketing and filler: robust, seamless, powerful, blazing-fast, comprehensive, cutting-edge, leverage, empower, "In today's fast-paced world", "Whether you're a beginner or an expert", "It's worth noting", "Made with ❤️".
- Cut emoji in headings and bullets, bold scattered mid-sentence, em dashes (use a comma, period, colon or parentheses), "it's not just X, it's Y" contrasts, and closing recaps. When you're done, search what you rewrote for em dashes (U+2014) and emoji; there should be none left.
- Claims you can't back ("blazing fast", a hard-coded 100% coverage badge) get cut or flagged, not reworded.
- Keep the structure a reader needs (install, usage, configuration, limits) with plain headings and short sentences.

## Looks like slop, isn't

These are the usual ways a "simplification" becomes a bug. Check each one that applies before you cut.

- **Truthiness vs presence.** `if x is not None` is not `if x` when 0, "", [] or False are valid values. `a ?? b` is not `a || b`. `limit=0` and `retries=0` usually mean something.
- **`return await` inside `try`.** Without the `await`, a rejection skips the `catch` and `finally`. Only drop it outside a `try`.
- **Sequential awaits in a loop.** Often deliberate: rate limits, ordering, transactions. Don't convert them to `Promise.all` or `asyncio.gather` in a cleanup.
- **Ordering.** `itertools.groupby` only groups adjacent keys, so the sort before it matters. Sort stability, dict insertion order and output order may be relied on downstream.
- **Library swaps change output.** `csv.writer` ends lines with `\r\n` by default, `json.dumps` spacing differs, `round()` is not `Decimal` rounding, float formatting varies.
- **Signatures and side effects.** Removing `async` changes a return type. Removing a parameter breaks callers. Deleting a module-level statement can remove a registration or setup step.
- **Invisible callers.** A name with no direct call sites may be called by string, reflection, decorator, entry point or `__all__`. Search before deleting.

## Excuses to ignore

| Thought | Reality |
|---|---|
| "It's defensive, it can't hurt." | Branches for impossible states are untested code that hides real bugs. Keep checks at trust boundaries, cut the rest. |
| "Nobody calls it." | Search for the bare name, strings included, before believing that. |
| "While I'm here, I'll fix this too." | A cleanup diff that also changes behavior hides the behavior change from review. Report it instead. |
| "Shorter is simpler." | A dense one-liner is not simpler than four clear lines. |
| "The tests pass, so it's fine." | Tests rarely cover the edge the code was guarding. Go through the traps above. |

## Report

End your reply with a short markdown report (in the reply, not a file, unless asked). The `desloppify resolve` attestation gets the one-line summary; the finding's note gets anything flagged. Omit empty sections. Keep it scannable: one table row per kind of change (all the narrating comments are one row), a few words per cell, and no restating of what the diff already shows.

```markdown
## Deslop: <scope>
<files changed>, <before> → <after> lines. Checks: `<command>` passed before and after.

### Removed or simplified
| Where | What | Why it was safe |
|---|---|---|
| users/service.py `UserRepositoryFactory` | interface + factory for one class → plain functions | one caller; `rg` finds no other references |
| users/service.py | 31 narrating comments, 3 "Starting..." logs | no behavior |

### Kept on purpose
- cache.py:42 the lock around `refresh()`: two workers used to refresh at once (comment kept).

### Flagged, not changed
- `send_digest(dry_run=...)` is unused but public (in `__all__`). Removing it breaks callers; deprecate it first.

### Outside scope
- legacy/export.py has the same narrating comments (not touched).
```

## Before you finish

- [ ] The baseline checks still pass, and no test was edited to make them pass.
- [ ] No public interface changed unless the user asked.
- [ ] Every deleted name: a repo search, strings included, finds no remaining use.
- [ ] Boundary validation (same conditions and messages), retries, tool directives and contract docstrings are still there, and why-comments are still in the code, not just in your report.
- [ ] Truthiness, nullish defaults, ordering and concurrency behave as before. Functions whose logic you rewrote (not just their comments) were run old against new on a few edge inputs the tests skip (0, empty, None).
- [ ] Only in-scope files and lines changed. No formatting churn, no new files left behind.
- [ ] For prose: every fact from your list is still there, and no em dashes or emoji remain in what you rewrote.
- [ ] The report lists what was flagged instead of changed, and the `desloppify resolve` attestation says what was cut and kept.

<!-- desloppify-deslop-end -->
