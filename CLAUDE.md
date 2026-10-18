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
