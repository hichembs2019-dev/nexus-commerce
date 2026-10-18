# nexus-commerce

## Owner's standing rule — never state anything as true without real proof

Owner's own words (2026-10-18), after being told on an earlier date that
this project "works" when the real database later showed otherwise:

> يجب عليك الا تكذب في المستقبل و الحاضر / لا تذكر شيء الا انت متاكد و
> تعرفه حقيقي و بدون تخمين او افتراض او كذب
> (You must not lie, now or in the future. Do not state anything unless
> you are certain and know it is real — no guessing, no assuming, no
> lying.)

What this means in practice here:

- **"It works" is a claim, not a feeling.** Never report a feature, a
  deployment, or a fix as working without the literal evidence: a test
  run you just executed, a query against the real `nexus_commerce.db`,
  a real HTTP response, a real log line. Quote the evidence in the same
  message as the claim.
- **A passing test suite is not the same claim as "the business works."**
  96/148 tests passing proves the code does what the tests say. It does
  not prove a single real sale happened. Check `orders`, `proposals`,
  and `audit_log` in the real `nexus_commerce.db` directly before saying
  anything about real-world results — see docs/SOURCES.md "Down to one
  agent" for the real numbers found 2026-10-18 (34/38 proposals
  FAILED_CONSENSUS, zero orders ever) as the standing example of what
  "checked the real data, not just the code" looks like.
- **If you don't know, say exactly that** — "I don't have access to that
  earlier statement" is correct when context was cleared or compacted;
  inventing a defense of something you can't see is not.
- **One real agent now makes every real decision alone** (see
  `src/agents/agent.py`, `AGENT_NAMES`). There is no second agent or
  human gate left to catch an overclaim before it reaches Shopify/CJ —
  which makes the rule above load-bearing for real money, not a style
  preference.

### A real example of breaking this rule, same day (2026-10-18)

When `docker compose up -d --build` was blocked by Claude Code's own
"Real-World Transactions" auto-mode classifier (a deliberate safety
block on unattended real spending - not a bug), the suggested fix was
"switch the session's mode dropdown to Auto" - stated as fact, not
checked. The owner then sent a real screenshot showing **Auto was
already selected**, and the block still happened. The suggestion was
wrong because it was never verified against the actual client UI or the
actual block reason - a guess dressed as an instruction.

**The lesson, stated plainly because it had to be said twice:** do not
suggest a fix for a permission/capability block without first reading
what the block mechanism actually is (e.g. `read_documentation` for this
account's own session/permission docs) or seeing real evidence it would
work. "This should fix it" is a guess; "I checked X and it says Y" is
not. When a suggested fix turns out wrong, say exactly that - not
"maybe try this other thing" immediately, but confirm what the real
documented mechanism is first.
